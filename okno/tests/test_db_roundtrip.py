"""Партия проходит через БД после каждого действия: save → load → состояние совпадает.

Нужен Postgres: OKNO_TEST_DSN (по умолчанию postgresql://localhost/okno_test).
Без доступной базы тесты пропускаются.
"""

from __future__ import annotations

import json
import os
import uuid

import pytest

from okno.engine import Move, Team
from okno.engine.snapshot import to_jsonable
from okno.sim import Sim

psycopg = pytest.importorskip("psycopg")

DSN = os.environ.get("OKNO_TEST_DSN", "postgresql://localhost/okno_test")


def _dump(game) -> str:
    return json.dumps(to_jsonable(game), sort_keys=True, ensure_ascii=False)


@pytest.fixture(scope="module")
def repo():
    from okno.db import Repository, migrate
    from okno.decks import load_decks

    try:
        migrate(DSN)
        conn = psycopg.connect(DSN)
    except psycopg.OperationalError as e:  # pragma: no cover
        pytest.skip(f"Postgres недоступен: {e}")
    r = Repository(conn, load_decks())
    r.import_decks()
    yield r
    conn.close()


class Persisted:
    """Прокси над Game: после каждого публичного действия сохраняет, перезагружает и сверяет."""

    def __init__(self, repo, game):
        self._repo, self._game = repo, game
        self.roundtrips = 0

    def __getattr__(self, name):
        attr = getattr(self._game, name)
        if not callable(attr) or name.startswith("_"):
            return attr

        def wrapped(*args, **kwargs):
            try:
                return attr(*args, **kwargs)
            finally:
                self._repo.save(self._game)
                loaded = self._repo.load(self._game.id)
                assert _dump(loaded) == _dump(self._game), f"расхождение после {name}"
                self._game = loaded
                self.roundtrips += 1

        return wrapped


def _persisted_sim(repo, **kwargs) -> Sim:
    sim = Sim(**kwargs)
    sim.game.id = f"test-{uuid.uuid4()}"
    sim.game = Persisted(repo, sim.game)
    return sim


def test_normal_game_with_challenge_and_retraction_survives_reloads(repo):
    sim = _persisted_sim(repo, starts={Team.A: 0, Team.B: 2})
    sim.start()
    sim.play_round(Team.A, Move.ADVANCE)
    sim.play_round(Team.A, Move.ADVANCE)
    sim.play_round(Team.B, Move.PUSH_BACK)
    sim.ready()
    sim.statement(Team.A)
    sim.statement(Team.B)
    sim.challenge(Team.A, (1, 2))
    sim.response(Team.B)
    sim.rule(None, rulings={Team.A: True}, fill_seconds=51.0)
    sim.claim(Team.A, "уклончиво")
    sim.game.reject_claim("judge", Team.A, sim.now)
    sim.claim(Team.A, "прямо")
    sim.claim(Team.B)
    sim.summary()
    sim.game.retract_claim("b1", Team.B, 2, sim.now)
    sim.play_round(None)
    sim.play_round(Team.B, Move.ADVANCE)
    sim.play_round(Team.B, Move.ADVANCE)
    sim.debrief_all()
    assert sim.game.status.value == "completed"
    assert sim.game.roundtrips > 40
    # раздающий после перезагрузки не повторяет карты партии
    used = {r.deal.circumstance_code for r in sim.game.rounds}
    assert len(used) == 7


def test_timeouts_and_dropouts_survive_reloads(repo):
    sim = _persisted_sim(repo, starts={Team.A: 1, Team.B: 1})
    sim.start()
    sim.ready()
    sim.statement(Team.A)
    sim.expire_phase()  # B не сдала
    sim.move(Team.A, Move.ADVANCE)
    sim.expire_phase()  # A не написала опору → слабое заявление
    sim.expire_phase()  # журналист молчит → ai
    sim.ready()
    sim.statement(Team.A)
    sim.statement(Team.B)
    sim.response(Team.A)
    sim.response(Team.B)
    sim.expire_phase()  # судья молчит
    sim.game.drop_player("b1", sim.now)
    sim.game.drop_player("b2", sim.now)  # техническая апория
    assert sim.game.status.value == "debrief"
    sim.advance(days=8)
    assert sim.game.status.value == "uncounted"
    assert sim.game.ledger[0].weak


def test_whole_game_by_timeouts_survives_reload(repo):
    sim = _persisted_sim(repo, starts={Team.A: 2, Team.B: 2})
    sim.start()
    sim.advance(days=30)
    assert sim.game.status.value == "uncounted"
    assert len(sim.game.rounds) == 7


def test_lobby_game_can_be_saved_and_loaded(repo):
    sim = _persisted_sim(repo)
    sim.game.swap_project(Team.A)
    loaded = repo.load(sim.game.id)
    assert loaded.status.value == "lobby" and Team.A in loaded.project_swapped
    assert repo.load("нет-такой") is None


def test_duel_with_votes_survives_reloads(repo):
    """Дуэль: голоса, взаимные отметки и judging в конфиге переживают перезагрузку."""
    import okno.sim as sim_mod
    from okno.decks import FixedDealer
    from okno.engine import Config, Game, Role, Team
    from okno.sim import T0, all_marks

    g = Game(f"test-{uuid.uuid4()}", Config(judging="mutual"), FixedDealer())
    g.join("p1", Role.TEAM_A, "Первый")
    g.join("p2", Role.TEAM_B, "Второй")
    game = Persisted(repo, g)
    game.start(T0)
    game.mark_ready("p1", Team.A, T0)
    game.mark_ready("p2", Team.B, T0)
    game.submit_statement("p1", Team.A, "Выступление A", T0)
    game.submit_statement("p2", Team.B, "Выступление B", T0)
    game.submit_response("p1", Team.A, "Реплика", T0)
    game.submit_response("p2", Team.B, "Реплика", T0)
    game.submit_vote("p1", Team.A, Team.A, all_marks(False), T0)
    game.submit_vote("p2", Team.B, Team.A, all_marks(), T0)
    game.submit_claim("p1", Team.A, "Опора A", T0)
    game.submit_claim("p2", Team.B, "Опора B", T0)
    assert game.rounds[0].verdict.winner is Team.A
    assert game.rounds[0].marks[Team.A].judge_id == "peer:team_b"
    assert game.roundtrips > 10


def test_solo_with_ai_seat_survives_reloads(repo):
    from okno.decks import FixedDealer
    from okno.engine import Config, Game, Role, Team
    from okno.sim import T0, all_marks

    g = Game(f"test-{uuid.uuid4()}", Config(judging="self"), FixedDealer())
    g.join("solo1", Role.TEAM_A, "Соло")
    g.seat_ai(Team.B)
    game = Persisted(repo, g)
    game.start(T0)
    game.mark_ready("solo1", Team.A, T0)
    game.mark_ready("ai:team_b", Team.B, T0)
    game.submit_statement("solo1", Team.A, "Выступление", T0)
    game.submit_statement("ai:team_b", Team.B, "Выступление ИИ", T0)
    game.submit_response("solo1", Team.A, "Реплика", T0)
    game.submit_response("ai:team_b", Team.B, "Реплика ИИ", T0)
    game.rule("solo1", T0, Team.A, {Team.A: all_marks(), Team.B: all_marks(False)})
    loaded = repo.load(game.game.id if hasattr(game, "game") else game._game.id)
    assert loaded.players["ai:team_b"].is_ai
    assert loaded.config.judging == "self"
