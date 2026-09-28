from datetime import UTC, datetime

import pytest

from okno.engine import Move, Team, Track
from okno.engine.types import TrackCause

AT = datetime(2026, 9, 21, tzinfo=UTC)


def test_start_positions_and_delta():
    t = Track()
    t.set_start(Team.A, 2)
    t.set_start(Team.B, 0)
    assert t.positions == {Team.A: 2, Team.B: 0}
    assert t.delta(Team.A) == 0


def test_step_from_zero_requires_two_consecutive_wins():
    t = Track()
    t.set_start(Team.A, 0)
    t.record_exchange(Team.A)  # серия 1
    assert not t.advance(Team.A, 1, AT, TrackCause.EXCHANGE_WON)
    assert t.positions[Team.A] == 0
    assert t.events[-1].cause is TrackCause.STREAK_PROGRESS
    t.record_exchange(Team.A)  # серия 2
    assert t.advance(Team.A, 2, AT, TrackCause.EXCHANGE_WON)
    assert t.positions[Team.A] == 1


def test_aporia_or_loss_breaks_streak():
    t = Track()
    t.set_start(Team.A, 0)
    t.record_exchange(Team.A)
    t.record_exchange(None)
    assert t.streak[Team.A] == 0
    t.record_exchange(Team.A)
    t.record_exchange(Team.B)
    assert t.streak == {Team.A: 0, Team.B: 1}


def test_middle_steps_cost_one_win_each():
    t = Track()
    t.set_start(Team.A, 1)
    for expected in (2, 3, 4, 5):
        t.record_exchange(Team.A)
        t.apply_move(Team.A, Move.ADVANCE, 1, AT)
        assert t.positions[Team.A] == expected
    assert t.reached_norm() is Team.A


def test_hard_bounds():
    t = Track()
    t.set_start(Team.A, 5)
    t.set_start(Team.B, 0)
    assert t.legal_moves(Team.A) == ()
    assert t.default_move(Team.A) is None
    assert not t.push_back(Team.B, 1, AT, TrackCause.PUSHED_BACK)
    assert not t.advance(Team.A, 1, AT, TrackCause.EXCHANGE_WON)


def test_push_back_moves_opponent_one_position():
    t = Track()
    t.set_start(Team.A, 1)
    t.set_start(Team.B, 3)
    t.record_exchange(Team.A)
    t.apply_move(Team.A, Move.PUSH_BACK, 1, AT)
    assert t.positions == {Team.A: 1, Team.B: 2}
    assert t.events[-1] .cause is TrackCause.PUSHED_BACK


def test_default_move_prefers_advance_then_push_back():
    t = Track()
    t.set_start(Team.A, 5)
    t.set_start(Team.B, 2)
    assert t.legal_moves(Team.A) == (Move.PUSH_BACK,)
    assert t.default_move(Team.A) is Move.PUSH_BACK


def test_illegal_start_position():
    with pytest.raises(Exception):
        Track().set_start(Team.A, 6)
