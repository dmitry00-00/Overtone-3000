"""Маршруты. Команда игрока выводится из его роли в партии, клиент её не передаёт."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ..engine.game import Game
from ..engine.types import IllegalAction, MarkCode, Move, Role, Team
from .auth import Identity, current_identity
from .service import GameService, NotFound
from .views import game_view

router = APIRouter(prefix="/api")


def service(request: Request) -> GameService:
    return request.app.state.service


def _team_of(game: Game, ident: Identity) -> Team:
    p = game.players.get(ident.player_id)
    if p is None or p.role.team is None:
        raise HTTPException(403, "действие доступно игроку команды")
    return p.role.team


def _run(svc: GameService, game_id: str, ident: Identity, fn) -> dict[str, Any]:
    try:
        game = svc.mutate(game_id, fn)
    except NotFound:
        raise HTTPException(404, "партии нет") from None
    except IllegalAction as e:
        raise HTTPException(409, str(e)) from None
    return game_view(game, ident.player_id, svc.decks)


@router.get("/health")
def health():
    """Проверка живости для хостинга. Без авторизации и без базы."""
    return {"ok": True}


# ----------------------------------------------------------------- игрок и список


@router.get("/me")
def me(ident: Identity = Depends(current_identity), svc: GameService = Depends(service)):
    svc.ensure_player(ident)
    return {"player_id": ident.player_id, "display_name": ident.display_name, "games": svc.games_of(ident.player_id)}


@router.get("/decks")
def decks(svc: GameService = Depends(service)):
    d = svc.decks
    return {
        "projects": [asdict(p) for p in d.projects.values()],
        "carriers": [asdict(c) for c in d.carriers.values()],
        "frames": [asdict(f) for f in d.frames.values()],
        "circumstances": [asdict(c) for c in d.circumstances.values()],
        "audiences": [asdict(a) for a in d.audiences.values()],
    }


# ----------------------------------------------------------------- лобби


class CreateGame(BaseModel):
    role: Role = Role.TEAM_A
    rounds: int | None = Field(default=None, ge=1, le=14)
    round_hours: float | None = Field(default=None, gt=0)


class JoinGame(BaseModel):
    role: Role


@router.post("/games")
def create_game(body: CreateGame, ident: Identity = Depends(current_identity), svc: GameService = Depends(service)):
    from datetime import timedelta

    from ..engine.types import Config

    kwargs: dict[str, Any] = {}
    if body.rounds:
        kwargs["rounds"] = body.rounds
    if body.round_hours:
        kwargs["round_duration"] = timedelta(hours=body.round_hours)
    game = svc.create(ident, body.role, Config(**kwargs))
    return game_view(game, ident.player_id, svc.decks)


@router.get("/games/{game_id}")
def get_game(game_id: str, ident: Identity = Depends(current_identity), svc: GameService = Depends(service)):
    try:
        game = svc.load(game_id)
    except NotFound:
        raise HTTPException(404, "партии нет") from None
    return game_view(game, ident.player_id, svc.decks)


@router.post("/games/{game_id}/join")
def join(game_id: str, body: JoinGame, ident: Identity = Depends(current_identity), svc: GameService = Depends(service)):
    svc.ensure_player(ident)
    return _run(svc, game_id, ident, lambda g, now: g.join(ident.player_id, body.role, ident.display_name))


@router.post("/games/{game_id}/start")
def start(game_id: str, ident: Identity = Depends(current_identity), svc: GameService = Depends(service)):
    def fn(g: Game, now):
        if ident.player_id not in g.players:
            raise IllegalAction("партию начинает участник")
        g.start(now)

    return _run(svc, game_id, ident, fn)


@router.post("/games/{game_id}/swap-project")
def swap_project(game_id: str, ident: Identity = Depends(current_identity), svc: GameService = Depends(service)):
    return _run(svc, game_id, ident, lambda g, now: g.swap_project(_team_of(g, ident)))


@router.post("/games/{game_id}/leave")
def leave(game_id: str, ident: Identity = Depends(current_identity), svc: GameService = Depends(service)):
    return _run(svc, game_id, ident, lambda g, now: g.drop_player(ident.player_id, now))


# ----------------------------------------------------------------- действия команды


class Text(BaseModel):
    body: str = Field(min_length=1)


class ChallengeIn(BaseModel):
    claim_numbers: list[int] = Field(min_length=2)
    argument: str = Field(min_length=1)


class MoveIn(BaseModel):
    move: Move


class Retract(BaseModel):
    number: int


@router.post("/games/{game_id}/ready")
def ready(game_id: str, ident: Identity = Depends(current_identity), svc: GameService = Depends(service)):
    return _run(svc, game_id, ident, lambda g, now: g.mark_ready(ident.player_id, _team_of(g, ident), now))


@router.post("/games/{game_id}/statement")
def statement(game_id: str, body: Text, ident: Identity = Depends(current_identity), svc: GameService = Depends(service)):
    return _run(svc, game_id, ident, lambda g, now: g.submit_statement(ident.player_id, _team_of(g, ident), body.body, now))


@router.post("/games/{game_id}/response")
def response(game_id: str, body: Text, ident: Identity = Depends(current_identity), svc: GameService = Depends(service)):
    return _run(svc, game_id, ident, lambda g, now: g.submit_response(ident.player_id, _team_of(g, ident), body.body, now))


@router.post("/games/{game_id}/challenge")
def challenge(game_id: str, body: ChallengeIn, ident: Identity = Depends(current_identity), svc: GameService = Depends(service)):
    return _run(
        svc, game_id, ident,
        lambda g, now: g.submit_challenge(ident.player_id, _team_of(g, ident), tuple(body.claim_numbers), body.argument, now),
    )


@router.post("/games/{game_id}/claim")
def claim(game_id: str, body: Text, ident: Identity = Depends(current_identity), svc: GameService = Depends(service)):
    return _run(svc, game_id, ident, lambda g, now: g.submit_claim(ident.player_id, _team_of(g, ident), body.body, now))


@router.post("/games/{game_id}/move")
def move(game_id: str, body: MoveIn, ident: Identity = Depends(current_identity), svc: GameService = Depends(service)):
    return _run(svc, game_id, ident, lambda g, now: g.choose_move(ident.player_id, _team_of(g, ident), body.move, now))


@router.post("/games/{game_id}/retract")
def retract(game_id: str, body: Retract, ident: Identity = Depends(current_identity), svc: GameService = Depends(service)):
    return _run(svc, game_id, ident, lambda g, now: g.retract_claim(ident.player_id, _team_of(g, ident), body.number, now))


# ----------------------------------------------------------------- судья и журналист


class Ruling(BaseModel):
    winner: Team | None = None
    marks: dict[Team, dict[MarkCode, bool]]
    challenge_rulings: dict[Team, bool] = Field(default_factory=dict)
    fill_seconds: float | None = None


class RejectClaim(BaseModel):
    team: Team


class SummaryIn(BaseModel):
    headline: str = Field(min_length=1)
    body: str = Field(min_length=1)


@router.post("/games/{game_id}/rule")
def rule(game_id: str, body: Ruling, ident: Identity = Depends(current_identity), svc: GameService = Depends(service)):
    return _run(
        svc, game_id, ident,
        lambda g, now: g.rule(ident.player_id, now, body.winner, body.marks, body.challenge_rulings or None, body.fill_seconds),
    )


@router.post("/games/{game_id}/reject-claim")
def reject_claim(game_id: str, body: RejectClaim, ident: Identity = Depends(current_identity), svc: GameService = Depends(service)):
    return _run(svc, game_id, ident, lambda g, now: g.reject_claim(ident.player_id, body.team, now))


@router.post("/games/{game_id}/summary")
def summary(game_id: str, body: SummaryIn, ident: Identity = Depends(current_identity), svc: GameService = Depends(service)):
    return _run(svc, game_id, ident, lambda g, now: g.publish_summary(ident.player_id, body.headline, body.body, now))


# ----------------------------------------------------------------- разбор


class DebriefNoteIn(BaseModel):
    atom_worked: str = Field(min_length=1)
    atom_missed: str = Field(min_length=1)


@router.post("/games/{game_id}/debrief-note")
def debrief_note(game_id: str, body: DebriefNoteIn, ident: Identity = Depends(current_identity), svc: GameService = Depends(service)):
    return _run(svc, game_id, ident, lambda g, now: g.submit_debrief_note(ident.player_id, body.atom_worked, body.atom_missed, now))


# ----------------------------------------------------------------- служебное


@router.post("/tick")
def tick(request: Request, svc: GameService = Depends(service)):
    """Ручной тик планировщика. Только в dev-режиме."""
    if not request.app.state.settings.dev_auth:
        raise HTTPException(404)
    return {"ticked": svc.tick_due()}
