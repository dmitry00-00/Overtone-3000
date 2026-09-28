"""Вызов на противоречие: вместо реплики, ставка на исход."""

import pytest

from okno.engine import IllegalAction, Move, Phase, Team
from okno.engine.types import TrackCause

from conftest import Sim


def _two_rounds_with_claims(sim: Sim) -> None:
    sim.play_round(Team.B, Move.ADVANCE)
    sim.play_round(Team.B, Move.ADVANCE)


def _to_response(sim: Sim) -> None:
    sim.ready()
    sim.statement(Team.A)
    sim.statement(Team.B)


def test_challenge_replaces_response_and_needs_two_existing_claims(sim: Sim):
    _two_rounds_with_claims(sim)
    _to_response(sim)
    with pytest.raises(IllegalAction, match="нет заявлений"):
        sim.challenge(Team.A, (1, 7))
    with pytest.raises(IllegalAction, match="двух"):
        sim.challenge(Team.A, (1, 1))
    sim.challenge(Team.A, (1, 2))
    with pytest.raises(IllegalAction, match="вместо"):
        sim.response(Team.A)


def test_challenge_upheld_pushes_back_and_gives_step(sim: Sim):
    _two_rounds_with_claims(sim)  # B: 1 → 3
    _to_response(sim)
    sim.challenge(Team.A, (1, 2))
    sim.response(Team.B)
    with pytest.raises(IllegalAction, match="нет решения"):
        sim.rule(Team.A)
    sim.rule(None, rulings={Team.A: True})
    assert sim.phase is Phase.LEDGER
    assert not sim.game.round.move_required(sim.game._ctx())  # ход определён вызовом
    assert sim.pos == {Team.A: 2, Team.B: 2}
    causes = [e.cause for e in sim.game.track.events[-2:]]
    assert causes == [TrackCause.CHALLENGE_UPHELD, TrackCause.CHALLENGE_UPHELD]
    assert all(c.challenged_in_round == 3 for c in sim.game.claims(Team.B))


def test_challenge_rejected_gives_opponent_free_step(sim: Sim):
    _two_rounds_with_claims(sim)  # B: 3
    _to_response(sim)
    sim.challenge(Team.A, (1, 2))
    sim.response(Team.B)
    sim.rule(Team.A, rulings={Team.A: False})  # «winner» судьи при вызове не применяется
    assert sim.pos == {Team.A: 1, Team.B: 4}
    assert sim.game.track.events[-1].cause is TrackCause.CHALLENGE_REJECTED
    assert sim.game.track.streak == {Team.A: 0, Team.B: 3}


def test_challenge_on_retracted_claim_is_impossible(sim: Sim):
    _two_rounds_with_claims(sim)
    sim.game.retract_claim("b1", Team.B, 1, sim.now)
    _to_response(sim)
    with pytest.raises(IllegalAction, match="отозвано"):
        sim.challenge(Team.A, (1, 2))


def test_ledger_check_above_three_cancels_step_and_rolls_back():
    """3 → 4 → 5: засчитанный вызов отменяет шаг и откатывает на позицию назад."""
    sim = Sim(starts={Team.A: 1, Team.B: 3})
    sim.start()
    sim.play_round(Team.B, Move.ADVANCE)  # B: 4, заявление 1
    sim.play_round(Team.B, Move.PUSH_BACK)  # A: 0, заявление 2
    _to_response(sim)
    sim.challenge(Team.A, (1, 2))
    sim.response(Team.B)
    sim.rule(None, rulings={Team.A: True})
    assert sim.pos[Team.B] == 3  # шаг на 5 не состоялся, откат
    assert sim.pos[Team.A] == 0  # у A серия 1: первая из двух побед для выхода из 0
    assert sim.game.track.events[-1].cause is TrackCause.STREAK_PROGRESS


def test_both_teams_challenge_resolved_independently(sim: Sim):
    _two_rounds_with_claims(sim)  # A: 1, B: 3; у каждой по два заявления
    _to_response(sim)
    sim.challenge(Team.A, (1, 2))
    sim.challenge(Team.B, (1, 2))
    sim.rule(None, rulings={Team.A: True, Team.B: False})
    # A засчитан: B −1, A +1. B отклонён: A +1 бесплатно.
    assert sim.pos == {Team.A: 3, Team.B: 2}


def test_unruled_challenge_on_judge_timeout_has_no_effect(sim: Sim):
    _two_rounds_with_claims(sim)
    _to_response(sim)
    sim.challenge(Team.A, (1, 2))
    sim.response(Team.B)
    sim.expire_phase()
    assert sim.game.round.challenges[Team.A].upheld is None
    assert sim.pos == {Team.A: 1, Team.B: 3}
