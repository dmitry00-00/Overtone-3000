"""Маршрут по фазам, когда все действуют вовремя."""

import pytest

from okno.engine import IllegalAction, MarkCode, Move, Phase, Team
from okno.engine.types import TrackCause

from conftest import JUDGE, Sim, all_marks


def test_opening_is_instant_and_lands_in_prep(sim: Sim):
    assert sim.phase is Phase.PREP
    log = [tr.to_phase for tr in sim.game.round.log]
    assert log == [Phase.PREP]
    assert sim.game.round.deal.circumstance_code == "О-01"
    assert sim.game.round.time_left(sim.now) == sim.game.config.phase_window(Phase.PREP)


def test_phase_ends_early_when_everyone_acted(sim: Sim):
    sim.ready(Team.A)
    assert sim.phase is Phase.PREP
    sim.ready(Team.B)
    assert sim.phase is Phase.STATEMENT


def test_statements_are_blind_until_both_submitted(sim: Sim):
    sim.ready()
    sim.statement(Team.A)
    assert sim.phase is Phase.STATEMENT  # соперник ещё не видит
    sim.statement(Team.B)
    assert sim.phase is Phase.RESPONSE
    assert [tr.to_phase for tr in sim.game.round.log[-2:]] == [Phase.REVEAL, Phase.RESPONSE]


def test_statement_can_be_edited_within_window(sim: Sim):
    sim.ready()
    sim.statement(Team.A, "первая версия")
    sim.statement(Team.A, "вторая версия")
    st = sim.game.round.statements[Team.A]
    assert st.body == "вторая версия"
    assert st.edit_count == 1
    assert st.prep_seconds == 0  # часы не двигали


def test_judge_card_requires_all_five_marks(sim: Sim):
    sim.ready()
    sim.statement(Team.A)
    sim.statement(Team.B)
    sim.response(Team.A)
    sim.response(Team.B)
    partial = {MarkCode.OPORA: True}
    with pytest.raises(IllegalAction, match="пять"):
        sim.game.rule(JUDGE, sim.now, Team.A, {Team.A: partial, Team.B: all_marks()})


def test_verdict_leads_to_ledger_and_winner_chooses_move(sim: Sim):
    sim.ready()
    sim.statement(Team.A)
    sim.statement(Team.B)
    sim.response(Team.A)
    sim.response(Team.B)
    sim.rule(Team.A, fill_seconds=42)
    assert sim.phase is Phase.LEDGER
    assert sim.game.round.verdict.fill_seconds == 42
    assert "team_a:move" in sim.game.round.pending(sim.game._ctx())
    with pytest.raises(IllegalAction):
        sim.move(Team.B, Move.ADVANCE)  # ход выбирает победитель
    sim.move(Team.A, Move.PUSH_BACK)
    sim.claim(Team.A)
    sim.claim(Team.B)
    assert sim.phase is Phase.SUMMARY
    assert sim.pos == {Team.A: 1, Team.B: 0}
    assert sim.game.round.verdict.move is Move.PUSH_BACK


def test_full_round_closes_and_opens_next(sim: Sim):
    sim.play_round(Team.A, Move.ADVANCE)
    assert sim.game.rounds[0].closed
    assert sim.game.round.index == 2
    assert sim.pos == {Team.A: 2, Team.B: 1}
    assert [c.number for c in sim.game.claims(Team.A)] == [1]
    assert sim.game.rounds[0].summary.author == "journalist"


def test_marks_and_track_are_separate_records(sim: Sim):
    sim.play_round(Team.B, Move.ADVANCE)
    rnd = sim.game.rounds[0]
    # судья отметил всё команде A, но обмен выиграла B: счета не смешиваются
    assert all(rnd.marks[Team.A].values.values())
    assert not any(rnd.marks[Team.B].values.values())
    assert sim.pos == {Team.A: 1, Team.B: 2}


def test_judge_may_rule_nobody_convinced(sim: Sim):
    sim.play_round(None)
    rnd = sim.game.rounds[0]
    assert rnd.is_aporia and rnd.verdict.aporia_reason.value == "judge_ruled_nobody"
    assert rnd.marks  # отметки при этом стоят
    assert sim.pos == {Team.A: 1, Team.B: 1}
    assert sim.game.track.streak == {Team.A: 0, Team.B: 0}


def test_claim_word_limit_and_judge_rejection(sim: Sim):
    sim.ready()
    sim.statement(Team.A)
    sim.statement(Team.B)
    sim.response(Team.A)
    sim.response(Team.B)
    sim.rule(Team.A)
    sim.move(Team.A, Move.ADVANCE)
    with pytest.raises(IllegalAction, match="15"):
        sim.claim(Team.A, " ".join(["слово"] * 16))
    sim.claim(Team.A, "уклончивая формулировка")
    sim.game.reject_claim(JUDGE, Team.A, sim.now)
    assert Team.A not in sim.game.round.claim_texts
    assert sim.game.round.claim_rejections[Team.A] == 1
    sim.claim(Team.A, "прямая формулировка")
    sim.claim(Team.B)
    assert sim.game.claims(Team.A)[0].text == "прямая формулировка"


def test_retraction_costs_a_step_and_counts_as_structural_plus(sim: Sim):
    sim.play_round(Team.A, Move.ADVANCE)
    assert sim.pos[Team.A] == 2
    sim.game.retract_claim("a2", Team.A, 1, sim.now)
    claim = sim.game.claims(Team.A)[0]
    assert claim.retracted and claim.retracted_in_round == 2
    assert sim.pos[Team.A] == 1
    assert sim.game.track.events[-1].cause is TrackCause.RETRACTION
    assert sim.game.structural[-1].atom == "revise_under_evidence"
    with pytest.raises(IllegalAction):
        sim.game.retract_claim("a1", Team.A, 1, sim.now)
    # номер отозванного не переиспользуется
    sim.play_round(Team.B, Move.ADVANCE)
    assert [c.number for c in sim.game.claims(Team.A)] == [1, 2]


def test_game_ends_on_norm_and_enters_debrief():
    sim = Sim(starts={Team.A: 3, Team.B: 1})
    sim.start()
    sim.play_round(Team.A, Move.ADVANCE)
    sim.play_round(Team.A, Move.ADVANCE)
    assert sim.game.track.positions[Team.A] == 5
    assert sim.game.status.value == "debrief"
    assert sim.game.outcome.winner is Team.A
    assert not sim.game.export_allowed
    sim.debrief_all()
    assert sim.game.status.value == "completed" and sim.game.export_allowed


def test_debrief_uncounted_after_window(sim: Sim):
    for _ in range(sim.game.config.rounds):
        sim.play_round(None)
    assert sim.game.status.value == "debrief"
    assert sim.game.outcome.is_aporia
    sim.advance(days=8)
    assert sim.game.status.value == "uncounted"
    assert not sim.game.export_allowed
