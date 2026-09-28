"""Соло (самосуд против ИИ) и дуэль (взаимный вердикт). Оба — тренировочные: без экспорта."""

import pytest

from okno.decks import FixedDealer
from okno.engine import Config, Game, IllegalAction, MarkCode, Move, Phase, Role, Team
from okno.sim import T0, all_marks


def solo_game(players=("solo1",)) -> Game:
    g = Game("solo", Config(judging="self"), FixedDealer({Team.A: 1, Team.B: 1}))
    for pid in players:
        g.join(pid, Role.TEAM_A, pid)
    g.seat_ai(Team.B)
    g.start(T0)
    return g


def duel_game() -> Game:
    g = Game("duel", Config(judging="mutual"), FixedDealer({Team.A: 1, Team.B: 1}))
    g.join("p1", Role.TEAM_A, "Первый")
    g.join("p2", Role.TEAM_B, "Второй")
    g.start(T0)
    return g


def _to_verdict(g: Game, a_pid: str = "p1", b_pid: str = "p2") -> None:
    g.mark_ready(a_pid, Team.A, T0)
    g.mark_ready(b_pid, Team.B, T0)
    g.submit_statement(a_pid, Team.A, "Выступление A", T0)
    g.submit_statement(b_pid, Team.B, "Выступление B", T0)
    g.submit_response(a_pid, Team.A, "Реплика A", T0)
    g.submit_response(b_pid, Team.B, "Реплика B", T0)


# ---------------------------------------------------------------- соло


def test_solo_starts_without_judge_and_ai_seat_is_active():
    g = solo_game()
    assert g.status.value == "in_progress"
    ai = g.players["ai:team_b"]
    assert ai.is_ai and ai.active and g.human_teams() == frozenset({Team.A})


def test_solo_self_judged_round_moves_track():
    g = solo_game()
    _to_verdict(g, "solo1", "ai:team_b")
    assert g.round.phase is Phase.VERDICT
    # судит сам игрок команды; ИИ судить не может
    with pytest.raises(IllegalAction):
        g.rule("ai:team_b", T0, Team.A, {Team.A: all_marks(), Team.B: all_marks(False)})
    g.rule("solo1", T0, Team.A, {Team.A: all_marks(), Team.B: all_marks(False)})
    g.choose_move("solo1", Team.A, Move.ADVANCE, T0)
    g.submit_claim("solo1", Team.A, "Опора соло", T0)
    g.submit_claim("ai:team_b", Team.B, "Опора ИИ", T0)
    assert g.track.positions[Team.A] == 2


def test_solo_friend_can_join_same_team():
    g = solo_game(players=("solo1", "friend"))
    assert {p.id for p in g.active_players(Team.A)} == {"solo1", "friend"}


def test_solo_debrief_ignores_ai_and_export_stays_closed():
    g = solo_game()
    for _ in range(g.config.rounds):
        _to_verdict(g, "solo1", "ai:team_b")
        g.rule("solo1", T0, None, {Team.A: all_marks(), Team.B: all_marks(False)})
        g.submit_claim("solo1", Team.A, "Опора", T0)
        g.submit_claim("ai:team_b", Team.B, "Опора", T0)
    assert g.status.value == "debrief"
    g.submit_debrief_note("solo1", "opora", "level", T0)
    assert g.status.value == "completed"  # отметка ИИ не нужна
    assert not g.export_allowed  # тренировка не отдаёт данных в профиль


def test_seat_ai_refuses_occupied_team():
    g = Game("x", Config(judging="self"), FixedDealer())
    g.join("h", Role.TEAM_B, "Человек")
    with pytest.raises(IllegalAction):
        g.seat_ai(Team.B)


# ---------------------------------------------------------------- дуэль


def test_duel_agreeing_votes_give_verdict_and_peer_marks():
    g = duel_game()
    _to_verdict(g)
    assert g.round.pending(g._ctx()) == {"team_a", "team_b"}
    with pytest.raises(IllegalAction, match="взаимный"):
        g.rule("p1", T0, Team.A, {Team.A: all_marks(), Team.B: all_marks()})
    g.submit_vote("p1", Team.A, Team.A, all_marks(False), T0)
    assert g.round.phase is Phase.VERDICT  # ждём второй голос
    g.submit_vote("p2", Team.B, Team.A, all_marks(), T0)
    rnd = g.rounds[-1]
    assert rnd.verdict.winner is Team.A and not rnd.is_aporia
    # отметки взаимные: карточку A заполнил голос B, карточку B — голос A
    assert rnd.marks[Team.A].judge_id == "peer:team_b" and all(rnd.marks[Team.A].values.values())
    assert rnd.marks[Team.B].judge_id == "peer:team_a" and not any(rnd.marks[Team.B].values.values())
    assert rnd.phase is Phase.LEDGER


def test_duel_disagreement_is_aporia():
    g = duel_game()
    _to_verdict(g)
    g.submit_vote("p1", Team.A, Team.A, all_marks(), T0)
    g.submit_vote("p2", Team.B, Team.B, all_marks(), T0)
    rnd = g.rounds[-1]
    assert rnd.is_aporia and rnd.verdict.aporia_reason.value == "no_consensus"
    assert g.track.positions == {Team.A: 1, Team.B: 1}


def test_duel_both_vote_nobody_is_agreed_aporia():
    g = duel_game()
    _to_verdict(g)
    g.submit_vote("p1", Team.A, None, all_marks(), T0)
    g.submit_vote("p2", Team.B, None, all_marks(), T0)
    assert g.rounds[-1].verdict.aporia_reason.value == "judge_ruled_nobody"


def test_duel_vote_timeout_is_no_verdict_without_marks():
    g = duel_game()
    _to_verdict(g)
    g.submit_vote("p1", Team.A, Team.A, all_marks(), T0)
    deadline = g.round.phase_deadline
    g.tick(deadline)
    rnd = g.rounds[-1]
    assert rnd.is_aporia and rnd.verdict.aporia_reason.value == "no_verdict"
    assert rnd.marks == {}  # один голос — не вердикт и не отметки


def test_duel_challenge_resolved_by_concession():
    g = duel_game()
    # два раунда с согласными вердиктами → у B два заявления
    for winner in (Team.B, Team.B):
        _to_verdict(g)
        g.submit_vote("p1", Team.A, winner, all_marks(), T0)
        g.submit_vote("p2", Team.B, winner, all_marks(), T0)
        g.choose_move("p2", Team.B, Move.ADVANCE, T0)
        g.submit_claim("p1", Team.A, "Опора A", T0)
        g.submit_claim("p2", Team.B, "Опора B", T0)
    assert g.track.positions[Team.B] == 3
    g.mark_ready("p1", Team.A, T0)
    g.mark_ready("p2", Team.B, T0)
    g.submit_statement("p1", Team.A, "Выступление A", T0)
    g.submit_statement("p2", Team.B, "Выступление B", T0)
    g.submit_challenge("p1", Team.A, (1, 2), "Несовместимы", T0)
    g.submit_response("p2", Team.B, "Реплика B", T0)
    # ответчик обязан ответить на вызов в голосе
    with pytest.raises(IllegalAction, match="вызов"):
        g.submit_vote("p2", Team.B, Team.B, all_marks(), T0)
    g.submit_vote("p1", Team.A, None, all_marks(), T0)
    g.submit_vote("p2", Team.B, None, all_marks(), T0, challenge_concede=True)
    rnd = g.rounds[-1]
    assert rnd.challenges[Team.A].upheld is True
    assert g.track.positions == {Team.A: 2, Team.B: 2}  # B откат, A шаг


def test_duel_export_stays_closed():
    g = duel_game()
    for _ in range(g.config.rounds):
        _to_verdict(g)
        g.submit_vote("p1", Team.A, None, all_marks(), T0)
        g.submit_vote("p2", Team.B, None, all_marks(), T0)
        g.submit_claim("p1", Team.A, "Опора", T0)
        g.submit_claim("p2", Team.B, "Опора", T0)
    g.submit_debrief_note("p1", "opora", "level", T0)
    g.submit_debrief_note("p2", "steelman", "ledger", T0)
    assert g.status.value == "completed" and not g.export_allowed
