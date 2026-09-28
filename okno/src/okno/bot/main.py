"""Бот: команды в чате + доставка outbox.

/new   — в группе: создать партию, привязанную к этому чату (автор — команда А)
/game  — ссылка на текущую партию чата
/start — в личке: приветствие и кнопка приложения; с deep-link ``game_<id>`` — ссылка в партию

Доставка: раз в несколько секунд забираем из outbox неотправленное и шлём
в чат партии (если привязан) или в личку каждому участнику с tg_id.
"""

from __future__ import annotations

import asyncio
import logging
from urllib.parse import urlencode

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, MenuButtonWebApp, Message, WebAppInfo

from ..api.auth import Identity
from ..api.service import GameService
from ..engine.types import Role
from . import texts

log = logging.getLogger("okno.bot")


class OknoBot:
    def __init__(self, token: str, service: GameService, webapp_url: str | None, app_short_name: str | None, poll_s: float = 5.0):
        self.bot = Bot(token)
        self.dp = Dispatcher()
        self.service = service
        self.webapp_url = webapp_url
        self.app_short_name = app_short_name
        self.poll_s = poll_s
        self.username: str | None = None
        self.dp.message.register(self.on_start, CommandStart())
        self.dp.message.register(self.on_new, Command("new"))
        self.dp.message.register(self.on_game, Command("game"))
        self.dp.message.register(self.on_bind, Command("bind"))

    # ----- ссылки -----

    def game_link(self, game_id: str) -> str | None:
        """Ссылка в партию. Direct-link Mini App, если в BotFather создан /newapp; иначе URL приложения."""
        if self.app_short_name and self.username:
            return f"https://t.me/{self.username}/{self.app_short_name}?startapp={game_id}"
        if self.webapp_url:
            return f"{self.webapp_url}?{urlencode({'game': game_id})}"
        return None

    def open_keyboard(self, game_id: str | None = None) -> InlineKeyboardMarkup | None:
        if not self.webapp_url:
            return None
        url = self.webapp_url if game_id is None else f"{self.webapp_url}?{urlencode({'game': game_id})}"
        return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Открыть «Окно»", web_app=WebAppInfo(url=url))]])

    # ----- команды -----

    @staticmethod
    def _identity(m: Message) -> Identity:
        u = m.from_user
        name = " ".join(filter(None, [u.first_name, u.last_name])) or u.username or str(u.id)
        return Identity(player_id=f"tg:{u.id}", display_name=name, tg_id=u.id)

    async def on_start(self, m: Message, command: CommandObject) -> None:
        if m.chat.type != "private":
            await m.answer(texts.START_GROUP)
            return
        arg = command.args or ""
        if arg.startswith("game_"):
            gid = arg[5:]
            await m.answer(f"Партия {gid}.", reply_markup=self.open_keyboard(gid))
            return
        await m.answer(texts.START_PRIVATE, reply_markup=self.open_keyboard())

    async def on_new(self, m: Message) -> None:
        if m.chat.type == "private":
            await m.answer("Партия создаётся в групповом чате: добавьте бота в чат и напишите там /new.")
            return
        ident = self._identity(m)
        game = await asyncio.to_thread(self.service.create, ident, Role.TEAM_A)
        await asyncio.to_thread(self.service.bind_chat, game.id, m.chat.id)
        link = self.game_link(game.id)
        text = (
            f"Партия {game.id} создана и привязана к этому чату. {ident.display_name} — команда А.\n"
            "Остальные входят через приложение и выбирают роль: команда А, команда Б, судья, журналист. "
            "Старт — когда есть обе команды и судья."
        )
        if link:
            text += f"\n{link}"
        else:
            text += "\nОткройте бота в личке и нажмите «Открыть «Окно»»."
        await m.answer(text)

    async def on_game(self, m: Message) -> None:
        games = await asyncio.to_thread(self.service.games_in_chat, m.chat.id)
        if not games:
            await m.answer("В этом чате нет партии. /new — создать.")
            return
        link = self.game_link(games[0])
        await m.answer(f"Партия {games[0]}." + (f"\n{link}" if link else ""))

    async def on_bind(self, m: Message, command: CommandObject) -> None:
        gid = (command.args or "").strip()
        if not gid:
            await m.answer("/bind <id партии> — привязать существующую партию к этому чату.")
            return
        try:
            await asyncio.to_thread(self.service.load, gid)
        except Exception:  # noqa: BLE001
            await m.answer("Партии с таким id нет.")
            return
        await asyncio.to_thread(self.service.bind_chat, gid, m.chat.id)
        await m.answer(f"Партия {gid} привязана к этому чату.")

    # ----- доставка -----

    async def deliver_once(self) -> int:
        items = await asyncio.to_thread(self.service.outbox_pending)
        sent: list[int] = []
        for item in items:
            text = texts.notification(item["kind"], item["payload"])
            chat_id, members = await asyncio.to_thread(self.service.delivery_targets, item["game_id"])
            targets = [chat_id] if chat_id else members
            kb = self.open_keyboard(item["game_id"]) if not chat_id else None
            for target in targets:
                try:
                    await self.bot.send_message(target, text, reply_markup=kb)
                except Exception:  # noqa: BLE001 — один недоступный чат не должен блокировать очередь
                    log.exception("не доставлено в %s", target)
            sent.append(item["id"])
        await asyncio.to_thread(self.service.outbox_mark_sent, sent)
        return len(sent)

    async def deliver_loop(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                await self.deliver_once()
            except Exception:  # noqa: BLE001
                log.exception("доставка упала")
            try:
                await asyncio.wait_for(stop.wait(), timeout=self.poll_s)
            except TimeoutError:
                pass

    async def setup_menu(self) -> None:
        """Кнопка меню в личке ведёт в Mini App; команды получают подсказки. Идемпотентно."""
        try:
            if self.webapp_url:
                await self.bot.set_chat_menu_button(
                    menu_button=MenuButtonWebApp(text="Окно", web_app=WebAppInfo(url=self.webapp_url))
                )
            await self.bot.set_my_commands([
                BotCommand(command="new", description="создать партию в этом чате"),
                BotCommand(command="game", description="текущая партия чата"),
                BotCommand(command="bind", description="привязать партию к чату"),
            ])
        except Exception:  # noqa: BLE001 — неудача настройки меню не должна останавливать бота
            log.exception("не удалось настроить меню бота")

    async def run(self, stop: asyncio.Event) -> None:
        me = await self.bot.get_me()
        self.username = me.username
        log.info("бот @%s", self.username)
        await self.setup_menu()
        delivery = asyncio.create_task(self.deliver_loop(stop))
        polling = asyncio.create_task(self.dp.start_polling(self.bot, handle_signals=False))
        await stop.wait()
        await self.dp.stop_polling()
        await asyncio.gather(polling, delivery, return_exceptions=True)
        await self.bot.session.close()
