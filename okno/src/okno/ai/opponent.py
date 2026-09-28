"""Мозг ИИ-соперника: выступления, реплики, опоры за ИИ-команду.

Два уровня. Шаблонный работает всегда и без сети: собирает связный текст из карт
раунда. LLM-уровень включается переменной OKNO_LLM_URL (локальный OpenAI-совместимый
endpoint по ТЗ — LM Studio, Ollama и т.п.); при любой ошибке падаем на шаблон.

Инвариант ТЗ: ИИ не судит. Здесь нет ни вердиктов, ни отметок, ни решений
по вызовам — только тексты игрока.
"""

from __future__ import annotations

import logging

from ..decks import Decks
from ..engine.game import Game
from ..engine.round import Round
from ..engine.types import Team

log = logging.getLogger("okno.ai")


class TemplateBrain:
    """Соперник-болванчик: предсказуемый, но играющий по правилам текст из карт."""

    def __init__(self, decks: Decks):
        self.decks = decks

    def _cards(self, game: Game, rnd: Round, team: Team):
        carrier_code, frame_code = rnd.deal.hands[team]
        return (
            self.decks.projects.get(game.projects.get(team, "")),
            self.decks.carriers.get(carrier_code),
            self.decks.frames.get(frame_code),
            self.decks.circumstances.get(rnd.deal.circumstance_code),
        )

    def statement(self, game: Game, rnd: Round, team: Team) -> str:
        project, carrier, frame, circ = self._cards(game, rnd, team)
        title = project.title if project else "наша мера"
        parts = []
        if frame:
            parts.append(f"Опора — {frame.title.lower()}: {frame.to_prove}.")
        parts.append(f"«{title}» — как раз такой случай.")
        if circ:
            parts.append(f"Событие недели — {circ.event.lower()} — делает это нагляднее: {circ.changes}.")
        if carrier:
            parts.append(f"За меру публично выступает {carrier.title.lower()} — {carrier.benefit.lower()}.")
        if project and project.objections[0]:
            parts.append(f"Мы слышим главное возражение — {project.objections[0].lower()} — и принимаем его всерьёз.")
        parts.append("Условие: если через год заявленный эффект не подтвердится открытыми данными, мы отзовём меру.")
        return " ".join(parts)

    def response(self, game: Game, rnd: Round, team: Team) -> str:
        opp = rnd.statements.get(team.other)
        _, _, frame, _ = self._cards(game, rnd, team)
        base = "Соперник говорит убедительно, но не в той плоскости"
        if frame:
            base += f": вопрос решается не там, а в плоскости «{frame.title.lower()}»"
        first = (opp.body.split(".")[0].strip().lower() if opp and opp.body else "")
        quote = f" Нам отвечают, что {first}." if first else ""
        return f"{base}.{quote} Наше условие отказа названо — пусть соперник назовёт своё."

    def claim(self, game: Game, rnd: Round, team: Team) -> str:
        _, _, frame, _ = self._cards(game, rnd, team)
        title = frame.title.lower() if frame else "названная ценность"
        return f"Наш ход держится на ценности «{title}», отказ — при провале эффекта"


class LLMBrain:
    """Локальная модель через OpenAI-совместимый endpoint. Ошибка любого рода → шаблон."""

    SYSTEM = (
        "Ты играешь одну из команд в игре «Окно» про продвижение спорной общественной меры. "
        "Пиши по-русски, кратко и по делу, без пафоса. Ты НИКОГДА не оцениваешь, кто победил, "
        "и не судишь аргументы — ты только выступаешь за свою сторону."
    )

    def __init__(self, url: str, model: str, decks: Decks, timeout_s: float = 60.0):
        self.url = url.rstrip("/")
        self.model = model
        self.fallback = TemplateBrain(decks)
        self.timeout_s = timeout_s

    def _chat(self, prompt: str, max_tokens: int = 400) -> str:
        import httpx

        r = httpx.post(
            f"{self.url}/chat/completions",
            json={
                "model": self.model,
                "messages": [{"role": "system", "content": self.SYSTEM}, {"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": 0.8,
            },
            timeout=self.timeout_s,
        )
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"].strip()
        if not text:
            raise ValueError("пустой ответ модели")
        return text

    def _context(self, game: Game, rnd: Round, team: Team) -> str:
        t = TemplateBrain.__new__(TemplateBrain)
        t.decks = self.fallback.decks
        project, carrier, frame, circ = t._cards(game, rnd, team)
        lines = [f"Ваш проект: {project.title if project else '—'}."]
        if project:
            lines.append(f"Известные возражения: {project.objections[0]}; {project.objections[1]}.")
        if frame:
            lines.append(f"Обязательная рамка: {frame.title} — доказать, {frame.to_prove}. Ловушка: {frame.trap}.")
        if carrier:
            lines.append(f"Ваш носитель: {carrier.title} (полезен: {carrier.benefit}; опасен: {carrier.danger}).")
        if circ:
            lines.append(f"Обстоятельство раунда: {circ.event} — {circ.changes}.")
        return "\n".join(lines)

    def statement(self, game: Game, rnd: Round, team: Team) -> str:
        try:
            return self._chat(
                self._context(game, rnd, team)
                + "\n\nНапиши выступление команды: 4–6 предложений. Обязательно: назови опору-ценность рамки, "
                "используй носителя, учти обстоятельство, возьми лучшее возражение всерьёз и назови условие, "
                "при котором вы откажетесь от меры. Только текст выступления."
            )
        except Exception:
            log.exception("LLM statement не удался, шаблон")
            return self.fallback.statement(game, rnd, team)

    def response(self, game: Game, rnd: Round, team: Team) -> str:
        opp = rnd.statements.get(team.other)
        try:
            return self._chat(
                self._context(game, rnd, team)
                + f"\n\nВыступление соперника:\n{opp.body if opp else '—'}\n\n"
                "Напиши короткую реплику (2–3 предложения) на выступление соперника от своей команды. "
                "Не оценивай, кто победил. Только текст реплики.",
                max_tokens=200,
            )
        except Exception:
            log.exception("LLM response не удался, шаблон")
            return self.fallback.response(game, rnd, team)

    def claim(self, game: Game, rnd: Round, team: Team) -> str:
        try:
            text = self._chat(
                self._context(game, rnd, team)
                + "\n\nСформулируй опорное заявление вашего раунда: одна фраза, НЕ БОЛЬШЕ пятнадцати слов, "
                "без кавычек и точки в конце. Только сама фраза.",
                max_tokens=60,
            )
            words = text.replace("\n", " ").split()
            return " ".join(words[:15]).strip('«»"').rstrip(".")
        except Exception:
            log.exception("LLM claim не удался, шаблон")
            return self.fallback.claim(game, rnd, team)


def make_brain(decks: Decks, llm_url: str | None, llm_model: str) -> TemplateBrain | LLMBrain:
    if llm_url:
        return LLMBrain(llm_url, llm_model, decks)
    return TemplateBrain(decks)
