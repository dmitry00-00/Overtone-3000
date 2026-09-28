"""Таблица таймаутов из раздела 4. Ни один не должен подвешивать партию."""

from okno.engine import AporiaReason, Config, Move, Phase, Team

from conftest import A1, A2, JUDGE, Sim


def test_prep_ends_by_deadline_without_readiness(sim: Sim):
    sim.expire_phase()
    assert sim.phase is Phase.STATEMENT
    assert sim.game.round.log[-1].by_timeout


def test_one_team_misses_statement_loses_exchange_without_marks(sim: Sim):
    sim.ready()
    sim.statement(Team.A)
    sim.expire_phase()
    rnd = sim.game.round
    assert rnd.forfeits == {Team.B}
    assert rnd.verdict.by_forfeit and rnd.verdict.winner is Team.A
    assert rnd.marks == {}  # структурных отметок нет ни у кого
    assert rnd.phase is Phase.LEDGER  # RESPONSE и VERDICT пропущены
    assert [t.to_phase for t in rnd.log[-2:]] == [Phase.REVEAL, Phase.LEDGER]
    # победитель выбирает ход, опору пишет только выступавшая команда
    assert rnd.pending(sim.game._ctx()) == {"team_a", "team_a:move"}
    sim.move(Team.A, Move.ADVANCE)
    sim.claim(Team.A)
    sim.summary()
    assert sim.pos == {Team.A: 2, Team.B: 1}
    assert [c.team for c in sim.game.ledger] == [Team.A]


def test_both_teams_miss_statement_is_aporia(sim: Sim):
    sim.expire_phase()  # PREP
    sim.expire_phase()  # STATEMENT
    rnd = sim.game.rounds[0]
    assert rnd.closed and rnd.is_aporia
    assert rnd.verdict.aporia_reason is AporiaReason.NO_STATEMENTS
    assert rnd.summary.author == "system"
    assert sim.pos == {Team.A: 1, Team.B: 1}
    assert sim.game.round.index == 2  # партия идёт дальше


def test_judge_misses_verdict_is_aporia_without_marks(sim: Sim):
    sim.ready()
    sim.statement(Team.A)
    sim.statement(Team.B)
    sim.response(Team.A)
    sim.response(Team.B)
    assert sim.phase is Phase.VERDICT
    sim.expire_phase()
    rnd = sim.game.round
    assert rnd.phase is Phase.LEDGER
    assert rnd.is_aporia and rnd.verdict.aporia_reason is AporiaReason.NO_VERDICT
    assert rnd.marks == {}
    assert rnd.pending(sim.game._ctx()) == {"team_a", "team_b"}  # хода нет, опоры пишут
    sim.claim(Team.A)
    sim.claim(Team.B)
    sim.summary()
    assert sim.pos == {Team.A: 1, Team.B: 1}
    assert sim.game.track.streak == {Team.A: 0, Team.B: 0}


def test_team_misses_ledger_gets_weak_placeholder(sim: Sim):
    sim.ready()
    sim.statement(Team.A)
    sim.statement(Team.B)
    sim.response(Team.A)
    sim.response(Team.B)
    sim.rule(Team.B)
    sim.claim(Team.A)
    sim.expire_phase()  # B не написала опору и не выбрала ход
    a, b = sim.game.claims(Team.A)[0], sim.game.claims(Team.B)[0]
    assert not a.weak
    assert b.weak and b.text == "команда не сформулировала опору"
    assert sim.game.rounds[0].verdict.move is Move.ADVANCE  # ход по умолчанию
    assert sim.pos == {Team.A: 1, Team.B: 2}


def test_winner_at_top_defaults_to_push_back():
    sim = Sim(starts={Team.A: 5, Team.B: 2}, config=Config(end_on_norm=False))
    sim.start()
    sim.ready()
    sim.statement(Team.A)
    sim.statement(Team.B)
    sim.response(Team.A)
    sim.response(Team.B)
    sim.rule(Team.A)
    assert not sim.game.round.move_required(sim.game._ctx())  # выбор не нужен — ход единственный
    sim.claim(Team.A)
    sim.claim(Team.B)
    assert sim.game.rounds[0].verdict.move is Move.PUSH_BACK
    assert sim.pos == {Team.A: 5, Team.B: 1}


def test_journalist_misses_summary_ai_publishes(sim: Sim):
    sim.ready()
    sim.statement(Team.A)
    sim.statement(Team.B)
    sim.response(Team.A)
    sim.response(Team.B)
    sim.rule(Team.A)
    sim.move(Team.A, Move.ADVANCE)
    sim.claim(Team.A)
    sim.claim(Team.B)
    assert sim.phase is Phase.SUMMARY
    sim.expire_phase()
    assert sim.game.rounds[0].summary.author == "ai"
    assert sim.game.round.index == 2


def test_no_journalist_in_game_ai_publishes_immediately():
    sim = Sim(journalist=False)
    sim.start()
    sim.play_round(Team.A, Move.ADVANCE)
    assert sim.game.rounds[0].summary.author == "ai"
    assert sim.game.round.index == 2


def test_team_continues_short_handed_when_one_player_drops(sim: Sim):
    sim.game.drop_player(A1, sim.now)
    sim.game.mark_ready(A2, Team.A, sim.now)
    sim.ready(Team.B)
    sim.game.submit_statement(A2, Team.A, "говорит оставшийся", sim.now)
    sim.statement(Team.B)
    assert sim.phase is Phase.RESPONSE


def test_team_with_no_active_players_is_technical_aporia(sim: Sim):
    sim.play_round(Team.A, Move.ADVANCE)
    sim.ready()
    sim.game.drop_player(A1, sim.now)
    sim.game.drop_player(A2, sim.now)
    rnd = sim.game.rounds[1]
    assert rnd.closed and rnd.verdict.aporia_reason is AporiaReason.TECHNICAL
    assert sim.game.technical_aporia_from == 2
    assert sim.game.status.value == "debrief"
    assert len(sim.game.rounds) == 2
    # разбор завершают оставшиеся активные
    sim.debrief_all()
    assert sim.game.status.value == "completed"


def test_judge_drops_every_round_is_aporia(sim: Sim):
    sim.game.drop_player(JUDGE, sim.now)
    sim.ready()
    sim.statement(Team.A)
    sim.statement(Team.B)
    sim.response(Team.A)
    sim.response(Team.B)
    rnd = sim.game.round
    assert rnd.phase is Phase.LEDGER and rnd.verdict.aporia_reason is AporiaReason.NO_VERDICT


def test_late_tick_cascades_through_expired_phases_with_chained_deadlines(sim: Sim):
    cfg = sim.game.config
    sim.advance(hours=48)  # никто не заходил двое суток
    rnd1 = sim.game.rounds[0]
    assert rnd1.closed and rnd1.verdict.aporia_reason is AporiaReason.NO_STATEMENTS
    # раунд 2 открылся ровно по дедлайну STATEMENT первого, а не в момент tick
    expected_close = sim.game.created_at + cfg.phase_window(Phase.PREP) + cfg.phase_window(Phase.STATEMENT)
    assert rnd1.log[-1].at == expected_close
    assert sim.game.rounds[1].opened_at == expected_close


def test_whole_game_by_timeouts_closes_correctly(sim: Sim):
    """Блокирующий критерий приёмки: партия целиком по таймаутам корректно закрывается."""
    cfg = sim.game.config
    per_round = cfg.phase_window(Phase.PREP) + cfg.phase_window(Phase.STATEMENT)
    sim.advance(seconds=(per_round * cfg.rounds).total_seconds() + 1)
    assert len(sim.game.rounds) == cfg.rounds
    assert all(r.closed and r.verdict.aporia_reason is AporiaReason.NO_STATEMENTS for r in sim.game.rounds)
    assert sim.game.status.value == "debrief"
    assert sim.game.outcome.is_aporia and sim.game.outcome.aporia_reason is AporiaReason.TIE
    assert sim.game.ledger == [] and sim.game.track.events == []
    sim.advance(days=8)
    assert sim.game.status.value == "uncounted"


def test_single_late_tick_reaches_uncounted(sim: Sim):
    sim.advance(days=30)
    assert sim.game.status.value == "uncounted"
    assert len(sim.game.rounds) == sim.game.config.rounds


def test_dropout_after_verdict_keeps_verdict_and_closes_ledger(sim: Sim):
    sim.ready()
    sim.statement(Team.A)
    sim.statement(Team.B)
    sim.response(Team.A)
    sim.response(Team.B)
    sim.rule(Team.A)
    sim.claim(Team.A)
    sim.game.drop_player("b1", sim.now)
    sim.game.drop_player("b2", sim.now)
    rnd = sim.game.rounds[0]
    assert rnd.closed and rnd.verdict.winner is Team.A and not rnd.is_aporia
    assert rnd.verdict.move is Move.ADVANCE  # ход по умолчанию применён при закрытии реестра
    assert sim.pos == {Team.A: 2, Team.B: 1}
    assert [c.team for c in sim.game.ledger] == [Team.A]  # выбывшая команда опоры не пишет
    assert sim.game.status.value == "debrief"
