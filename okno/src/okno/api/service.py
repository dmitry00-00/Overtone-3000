"""Единица работы: загрузить партию с блокировкой → действие → сохранить → уведомления.

Всё, что меняет партию (действия игроков, тики планировщика), проходит через
``GameService.mutate``. Изменение фазы/статуса после действия попадает в outbox —
оттуда его заберёт бот.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable

import psycopg
from psycopg_pool import ConnectionPool

from ..db.repo import Repository
from ..decks import DeckDealer, Decks
from ..engine.game import Game
from ..engine.types import Config, GameStatus, IllegalAction, Role
from .auth import Identity


class NotFound(Exception):
    pass


def now_utc() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class _Marker:
    status: str
    round_index: int | None
    phase: str | None

    @classmethod
    def of(cls, game: Game) -> "_Marker":
        rnd = game.rounds[-1] if game.rounds else None
        return cls(game.status.value, rnd.index if rnd else None, rnd.phase.value if rnd else None)


class GameService:
    def __init__(self, pool: ConnectionPool, decks: Decks):
        self.pool = pool
        self.decks = decks

    # ----- чтение -----

    def load(self, game_id: str) -> Game:
        with self.pool.connection() as conn:
            game = Repository(conn, self.decks).load(game_id)
        if game is None:
            raise NotFound(game_id)
        return game

    def games_of(self, player_id: str) -> list[dict]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                """
                select g.id, g.status, m.role, g.updated_at,
                       (select max(index) from rounds r where r.game_id = g.id) as round_index,
                       (select phase from rounds r where r.game_id = g.id order by index desc limit 1) as phase
                from games g join memberships m on m.game_id = g.id
                where m.player_id = %s order by g.updated_at desc
                """,
                (player_id,),
            ).fetchall()
        return [
            {"id": r[0], "status": r[1], "role": r[2], "updated_at": r[3].isoformat(), "round_index": r[4], "phase": r[5]}
            for r in rows
        ]

    # ----- запись -----

    def ensure_player(self, ident: Identity) -> None:
        with self.pool.connection() as conn:
            conn.execute(
                """
                insert into players (id, tg_id, display_name) values (%s, %s, %s)
                on conflict (id) do update set display_name = excluded.display_name, tg_id = coalesce(excluded.tg_id, players.tg_id)
                """,
                (ident.player_id, ident.tg_id, ident.display_name),
            )

    def create(self, ident: Identity, role: Role, config: Config | None = None) -> Game:
        self.ensure_player(ident)
        game = Game(id=uuid.uuid4().hex[:12], config=config or Config(), dealer=DeckDealer(self.decks))
        game.join(ident.player_id, role, ident.display_name)
        game.draw_projects()  # карты проектов видны в лобби: до старта возможен один обмен
        with self.pool.connection() as conn:
            Repository(conn, self.decks).save(game)
        return game

    def mutate(self, game_id: str, action: Callable[[Game, datetime], None], now: datetime | None = None) -> Game:
        """Загрузить с блокировкой, применить действие, сохранить, записать уведомления."""
        now = now or now_utc()
        with self.pool.connection() as conn, conn.transaction():
            repo = Repository(conn, self.decks)
            game = repo.load(game_id, for_update=True)
            if game is None:
                raise NotFound(game_id)
            before = _Marker.of(game)
            action(game, now)
            repo.save(game)
            after = _Marker.of(game)
            if before != after:
                self._notify(conn, game, before, after)
        return game

    def tick_due(self, now: datetime | None = None) -> list[str]:
        """Партии, у которых истёк дедлайн фазы или разбора. Вызывает планировщик."""
        now = now or now_utc()
        with self.pool.connection() as conn:
            rows = conn.execute(
                """
                select g.id from games g
                where (g.status = 'in_progress' and exists (
                          select 1 from rounds r where r.game_id = g.id and r.phase_deadline is not null and r.phase_deadline <= %s
                          and r.index = (select max(index) from rounds r2 where r2.game_id = g.id)))
                   or (g.status = 'debrief' and exists (select 1 from debriefs d where d.game_id = g.id and d.deadline <= %s))
                """,
                (now, now),
            ).fetchall()
        ticked = []
        for (gid,) in rows:
            self.mutate(gid, lambda g, t: g.tick(t), now)
            ticked.append(gid)
        return ticked

    # ----- уведомления -----

    def _notify(self, conn: psycopg.Connection, game: Game, before: _Marker, after: _Marker) -> None:
        rnd = game.rounds[-1] if game.rounds else None
        pending = sorted(rnd.pending(game._ctx())) if rnd and game.status is GameStatus.IN_PROGRESS else []
        if before.status != after.status:
            kind = {"in_progress": "game_started", "debrief": "debrief_started", "completed": "game_completed", "uncounted": "game_uncounted"}.get(after.status, "status_changed")
        else:
            kind = "phase_changed"
        payload = {
            "status": after.status,
            "round_index": after.round_index,
            "phase": after.phase,
            "deadline": rnd.phase_deadline.isoformat() if rnd and rnd.phase_deadline else None,
            "pending": pending,
            "by_timeout": bool(rnd and rnd.log and rnd.log[-1].by_timeout),
        }
        conn.execute(
            "insert into outbox (game_id, player_id, kind, payload) values (%s, null, %s, %s)",
            (game.id, kind, json.dumps(payload, ensure_ascii=False)),
        )

    # ----- чат партии (для бота) -----

    def bind_chat(self, game_id: str, chat_id: int) -> None:
        with self.pool.connection() as conn:
            conn.execute("update games set chat_id = %s where id = %s", (chat_id, game_id))

    def games_in_chat(self, chat_id: int) -> list[str]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                "select id from games where chat_id = %s and status in ('lobby', 'in_progress', 'debrief') order by updated_at desc",
                (chat_id,),
            ).fetchall()
        return [r[0] for r in rows]

    def delivery_targets(self, game_id: str) -> tuple[int | None, list[int]]:
        """Куда слать уведомление: чат партии и/или личные чаты активных участников."""
        with self.pool.connection() as conn:
            chat = conn.execute("select chat_id from games where id = %s", (game_id,)).fetchone()
            rows = conn.execute(
                "select p.tg_id from memberships m join players p on p.id = m.player_id "
                "where m.game_id = %s and m.dropped_at is null and p.tg_id is not null",
                (game_id,),
            ).fetchall()
        return (chat[0] if chat else None), [r[0] for r in rows]

    def outbox_pending(self, limit: int = 100) -> list[dict]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                "select id, game_id, player_id, kind, payload, created_at from outbox where sent_at is null order by id limit %s",
                (limit,),
            ).fetchall()
        return [{"id": r[0], "game_id": r[1], "player_id": r[2], "kind": r[3], "payload": r[4], "created_at": r[5]} for r in rows]

    def outbox_mark_sent(self, ids: list[int]) -> None:
        if not ids:
            return
        with self.pool.connection() as conn:
            conn.execute("update outbox set sent_at = now() where id = any(%s)", (ids,))


def illegal_to_http(exc: IllegalAction):
    from fastapi import HTTPException

    return HTTPException(409, str(exc))
