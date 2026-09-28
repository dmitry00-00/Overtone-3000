"""Проекция партии для конкретного игрока.

Здесь живут правила видимости: выступления слепые до REVEAL, реплики и вызовы —
до конца RESPONSE, черновик опоры соперника — до закрытия реестра, отметки
соперника — до разбора, карта публики — у судьи и журналиста до закрытия раунда.
Первым полем идёт ``prompt`` — ответ на «что от меня ждут прямо сейчас».
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any

from ..decks import Decks
from ..engine.game import Game
from ..engine.round import Round
from ..engine.types import GameStatus, Phase, Player, Role, Team


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _card(cards: dict, code: str) -> dict[str, Any]:
    c = cards.get(code)
    return asdict(c) if c else {"code": code}


PHASE_TITLES = {
    Phase.PREP: "Подготовка",
    Phase.STATEMENT: "Выступление",
    Phase.RESPONSE: "Реплика",
    Phase.VERDICT: "Вердикт",
    Phase.LEDGER: "Реестр",
    Phase.SUMMARY: "Сводка",
    Phase.CLOSED: "Раунд закрыт",
}


def prompt_for(game: Game, me: Player | None) -> dict[str, Any]:
    """Одна строка о том, что сейчас требуется от игрока. Самый важный элемент продукта."""
    if me is None:
        return {"kind": "spectator", "text": "Вы не участник этой партии", "deadline": None}
    if not me.active:
        return {"kind": "dropped", "text": "Вы выбыли из партии", "deadline": None}
    match game.status:
        case GameStatus.LOBBY:
            return {"kind": "lobby", "text": "Партия ещё не началась", "deadline": None}
        case GameStatus.DEBRIEF:
            if me.id in game.debrief_notes:
                return {"kind": "wait", "text": "Разбор: ждём отметки остальных", "deadline": _iso(game.debrief_deadline)}
            return {"kind": "debrief", "text": "Разбор: назовите сработавший и пропущенный атом", "deadline": _iso(game.debrief_deadline)}
        case GameStatus.COMPLETED:
            return {"kind": "done", "text": "Партия завершена и разобрана", "deadline": None}
        case GameStatus.UNCOUNTED:
            return {"kind": "done", "text": "Партия закрыта без разбора и не засчитана", "deadline": None}

    rnd = game.round
    ctx = game._ctx()
    pending = rnd.pending(ctx)
    deadline = _iso(rnd.phase_deadline)
    team = me.role.team
    tv = team.value if team else None

    def waiting(text: str) -> dict[str, Any]:
        return {"kind": "wait", "text": text, "deadline": deadline}

    match rnd.phase:
        case Phase.PREP:
            if team and tv in pending:
                return {"kind": "prep", "text": "Подготовка: обсудите ход и отметьте готовность", "deadline": deadline}
            return waiting("Подготовка: ждём готовности соперника" if team else "Команды готовятся")
        case Phase.STATEMENT:
            if team and tv in pending:
                return {"kind": "statement", "text": "Сдайте выступление — соперник его не видит до раскрытия", "deadline": deadline}
            return waiting("Ждём выступление соперника" if team else "Команды пишут выступления")
        case Phase.RESPONSE:
            if team and tv in pending:
                return {"kind": "response", "text": "Реплика — или вызов на противоречие вместо неё", "deadline": deadline}
            return waiting("Ждём реплику соперника" if team else "Команды отвечают")
        case Phase.VERDICT:
            match game.config.judging:
                case "self":
                    if team:
                        return {"kind": "verdict", "text": "Самосуд: решите честно, кто убедил, и отметьте обе карточки", "deadline": deadline}
                    return waiting("Команда судит свой обмен")
                case "mutual":
                    if team and tv in pending:
                        return {"kind": "verdict", "text": "Взаимный вердикт: кто убедил — и пять отметок сопернику", "deadline": deadline}
                    return waiting("Ждём вердикт соперника" if team else "Команды выносят взаимный вердикт")
                case _:
                    if me.role is Role.JUDGE:
                        return {"kind": "verdict", "text": "Вынесите вердикт и отметьте пять пунктов каждой команде", "deadline": deadline}
                    return waiting("Ждём вердикт судьи")
        case Phase.LEDGER:
            if team:
                needs_claim = tv in pending
                needs_move = f"{tv}:move" in pending
                if needs_claim and needs_move:
                    return {"kind": "ledger", "text": "Запишите опорное заявление и выберите ход", "deadline": deadline}
                if needs_claim:
                    return {"kind": "ledger", "text": "Запишите опорное заявление — до пятнадцати слов", "deadline": deadline}
                if needs_move:
                    return {"kind": "move", "text": "Выберите ход: шаг себе или откат сопернику", "deadline": deadline}
                return waiting("Ждём заявление соперника")
            if me.role is Role.JUDGE:
                return waiting("Команды пишут опоры; уклончивую можно отклонить")
            return waiting("Команды пишут опоры")
        case Phase.SUMMARY:
            if me.role is Role.JOURNALIST:
                return {"kind": "summary", "text": "Опубликуйте сводку раунда", "deadline": deadline}
            return waiting("Ждём сводку журналиста")
    return waiting("Раунд закрывается")


def round_view(game: Game, rnd: Round, me: Player | None, decks: Decks) -> dict[str, Any]:
    my_team = me.role.team if me else None
    is_judge = me is not None and me.role is Role.JUDGE
    is_press = me is not None and me.role is Role.JOURNALIST
    after = lambda phase: _phase_index(rnd.phase) > _phase_index(phase)  # noqa: E731
    closed = rnd.closed
    debrief = game.status in (GameStatus.DEBRIEF, GameStatus.COMPLETED, GameStatus.UNCOUNTED)

    statements = {}
    for team, st in rnd.statements.items():
        if team is my_team or after(Phase.STATEMENT):
            statements[team.value] = {
                "body": st.body, "submitted_at": _iso(st.submitted_at), "author_id": st.author_id, "edit_count": st.edit_count,
            }
    responses = {}
    challenges = {}
    if after(Phase.RESPONSE) or my_team is not None:
        for team, r in rnd.responses.items():
            if team is my_team or after(Phase.RESPONSE):
                responses[team.value] = {"body": r.body, "submitted_at": _iso(r.submitted_at)}
        for team, ch in rnd.challenges.items():
            if team is my_team or after(Phase.RESPONSE):
                challenges[team.value] = {
                    "claim_numbers": list(ch.claim_numbers), "argument": ch.argument, "upheld": ch.upheld, "ruled_at": _iso(ch.ruled_at),
                }
    # судья видит вызовы сразу: они нужны ему для карточки
    if is_judge:
        challenges = {
            t.value: {"claim_numbers": list(c.claim_numbers), "argument": c.argument, "upheld": c.upheld, "ruled_at": _iso(c.ruled_at)}
            for t, c in rnd.challenges.items()
        }

    votes: dict[str, Any] = {}
    if my_team is not None and my_team in rnd.votes:
        v = rnd.votes[my_team]
        votes["mine"] = {
            "winner": v.winner.value if v.winner else None,
            "opponent_marks": {c.value: val for c, val in v.opponent_marks.items()},
            "challenge_concede": v.challenge_concede,
        }
    if my_team is not None:
        votes["opponent_submitted"] = my_team.other in rnd.votes

    verdict = None
    if rnd.verdict is not None:
        v = rnd.verdict
        verdict = {
            "winner": v.winner.value if v.winner else None, "is_aporia": v.is_aporia,
            "aporia_reason": v.aporia_reason.value if v.aporia_reason else None, "by_forfeit": v.by_forfeit,
            "move": v.move.value if v.move else None, "ruled_at": _iso(v.ruled_at),
        }
    marks = {}
    for team, m in rnd.marks.items():
        if team is my_team or is_judge or debrief:
            marks[team.value] = {code.value: val for code, val in m.values.items()}

    claim_drafts = {}
    for team, text in rnd.claim_texts.items():
        if team is my_team or is_judge:
            claim_drafts[team.value] = text

    hands = {t.value: {"carrier": _card(decks.carriers, c), "frame": _card(decks.frames, f)} for t, (c, f) in rnd.deal.hands.items()}
    # Публика — линза судейства. Без судьи (соло, дуэль) судят команды — им она и видна.
    judges_themselves = game.config.judging != "judge" and my_team is not None
    audience = _card(decks.audiences, rnd.deal.audience_code) if (is_judge or is_press or closed or judges_themselves) else None

    return {
        "index": rnd.index,
        "phase": rnd.phase.value,
        "phase_title": PHASE_TITLES.get(rnd.phase, rnd.phase.value),
        "phase_started_at": _iso(rnd.phase_started_at),
        "deadline": _iso(rnd.phase_deadline),
        "opened_at": _iso(rnd.opened_at),
        "circumstance": _card(decks.circumstances, rnd.deal.circumstance_code),
        "audience": audience,
        "hands": hands,
        "ready": sorted(t.value for t in rnd.ready),
        "forfeits": sorted(t.value for t in rnd.forfeits),
        "statements": statements,
        "responses": responses,
        "challenges": challenges,
        "verdict": verdict,
        "marks": marks,
        "claim_drafts": claim_drafts,
        "votes": votes,
        "claim_rejections": {t.value: n for t, n in rnd.claim_rejections.items()},
        "move_choice": rnd.move_choice.value if rnd.move_choice else None,
        "summary": asdict(rnd.summary) | {"published_at": _iso(rnd.summary.published_at)} if rnd.summary else None,
        "pending": sorted(rnd.pending(game._ctx())) if game.status is GameStatus.IN_PROGRESS else [],
        "transitions": [
            {"from": t.from_phase.value, "to": t.to_phase.value, "at": _iso(t.at), "by_timeout": t.by_timeout} for t in rnd.log
        ],
    }


_ORDER = list(Phase)


def _phase_index(phase: Phase) -> int:
    return _ORDER.index(phase)


def game_view(game: Game, player_id: str, decks: Decks) -> dict[str, Any]:
    me = game.players.get(player_id)
    my_team = me.role.team if me else None
    current = game.rounds[-1] if game.rounds and game.status is GameStatus.IN_PROGRESS else None
    debrief = game.status in (GameStatus.DEBRIEF, GameStatus.COMPLETED, GameStatus.UNCOUNTED)

    ledger = [
        {
            "team": c.team.value, "number": c.number, "round_index": c.round_index, "text": c.text, "weak": c.weak,
            "retracted": c.retracted, "retracted_in_round": c.retracted_in_round, "challenged_in_round": c.challenged_in_round,
        }
        for c in game.ledger
    ]
    legal_moves: list[str] = []
    if current is not None and my_team is not None and current.move_required(game._ctx()) and current.verdict and current.verdict.winner is my_team:
        legal_moves = [m.value for m in game.track.legal_moves(my_team)]

    view: dict[str, Any] = {
        "prompt": prompt_for(game, me),
        "game": {
            "id": game.id,
            "status": game.status.value,
            "created_at": _iso(game.created_at),
            "judging": game.config.judging,
            "rounds_total": game.config.rounds,
            "rounds_played": len(game.rounds),
            "technical_aporia_from": game.technical_aporia_from,
            "outcome": (
                {
                    "winner": game.outcome.winner.value if game.outcome.winner else None,
                    "is_aporia": game.outcome.is_aporia,
                    "aporia_reason": game.outcome.aporia_reason.value if game.outcome.aporia_reason else None,
                    "positions": {t.value: p for t, p in game.outcome.positions.items()},
                    "deltas": {t.value: d for t, d in game.outcome.deltas.items()},
                }
                if game.outcome
                else None
            ),
        },
        "me": {"player_id": player_id, "role": me.role.value if me else None, "team": my_team.value if my_team else None, "display_name": me.display_name if me else None},
        "players": [
            {"id": p.id, "display_name": p.display_name, "role": p.role.value, "team": p.role.team.value if p.role.team else None, "active": p.active, "is_ai": p.is_ai}
            for p in game.players.values()
        ],
        "projects": {
            t.value: _card(decks.projects, code) | {"swapped": t in game.project_swapped} for t, code in game.projects.items()
        },
        "track": {
            "size": game.track.size,
            "positions": {t.value: p for t, p in game.track.positions.items()},
            "start": {t.value: p for t, p in game.track.start.items()},
            "streak": {t.value: s for t, s in game.track.streak.items()},
            "events": [
                {"round_index": e.round_index, "team": e.team.value, "from": e.position_from, "to": e.position_to, "cause": e.cause.value, "at": _iso(e.at)}
                for e in game.track.events
            ],
        },
        "round": round_view(game, current, me, decks) if current else None,
        "rounds": [round_view(game, r, me, decks) for r in game.rounds if r.closed],
        "ledger": ledger,
        "contradiction_hint": game.contradiction_hint(my_team) if my_team else None,
        "legal_moves": legal_moves,
        "structural_mine": [
            {"round_index": e.round_index, "atom": e.atom, "at": _iso(e.at)} for e in game.structural if e.team is my_team
        ],
        "debrief": (
            {
                "started_at": _iso(game.debrief_started_at),
                "deadline": _iso(game.debrief_deadline),
                "completed_at": _iso(game.debrief_completed_at),
                "notes_from": sorted(game.debrief_notes),
                "waiting_for": sorted(p.id for p in game.active_players() if not p.is_ai and p.id not in game.debrief_notes),
                "track_replay": [
                    {"round_index": e.round_index, "team": e.team.value, "from": e.position_from, "to": e.position_to, "cause": e.cause.value, "statement": body}
                    for e, body in game.track_replay()
                ],
                "export_allowed": game.export_allowed,
            }
            if debrief
            else None
        ),
    }
    return view
