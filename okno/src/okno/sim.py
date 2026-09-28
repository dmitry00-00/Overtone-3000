"""Симулятор партии с управляемыми часами. Общий для тестов и скриптовых прогонов."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from .decks import FixedDealer
from .engine import Config, Game, MarkCode, Move, Phase, Role, Team

T0 = datetime(2026, 9, 21, 9, 0, tzinfo=UTC)

A1, A2, B1, B2, JUDGE, PRESS = "a1", "a2", "b1", "b2", "judge", "press"


def all_marks(value: bool = True) -> dict[MarkCode, bool]:
    return {code: value for code in MarkCode}


class Sim:
    """Обёртка над Game: часы, короткие имена действий, прогон типовых раундов."""

    def __init__(self, config: Config | None = None, starts: dict[Team, int] | None = None, journalist: bool = True):
        self.now = T0
        self.game = Game("g", config or Config(), FixedDealer(starts))
        g = self.game
        g.join(A1, Role.TEAM_A, "Аня")
        g.join(A2, Role.TEAM_A, "Артём")
        g.join(B1, Role.TEAM_B, "Борис")
        g.join(B2, Role.TEAM_B, "Белла")
        g.join(JUDGE, Role.JUDGE, "Судья")
        if journalist:
            g.join(PRESS, Role.JOURNALIST, "Журналист")

    # ----- часы -----

    def advance(self, **kwargs) -> None:
        self.now += timedelta(**kwargs)
        self.game.tick(self.now)

    def expire_phase(self) -> None:
        """Дождаться дедлайна текущей фазы."""
        deadline = self.game.round.phase_deadline
        assert deadline is not None, "у фазы нет дедлайна"
        self.now = deadline
        self.game.tick(self.now)

    # ----- состояние -----

    @property
    def phase(self) -> Phase:
        return self.game.round.phase

    @property
    def pos(self) -> dict[Team, int]:
        return dict(self.game.track.positions)

    # ----- действия -----

    def start(self) -> None:
        self.game.start(self.now)

    def ready(self, *teams: Team) -> None:
        for t in teams or tuple(Team):
            self.game.mark_ready(A1 if t is Team.A else B1, t, self.now)

    def statement(self, team: Team, body: str | None = None) -> None:
        pid = A1 if team is Team.A else B1
        self.game.submit_statement(pid, team, body or f"Выступление {team.value} в раунде {self.game.round.index}", self.now)

    def response(self, team: Team, body: str = "Реплика") -> None:
        self.game.submit_response(A1 if team is Team.A else B1, team, body, self.now)

    def challenge(self, team: Team, numbers: tuple[int, ...], argument: str = "Несовместимы") -> None:
        self.game.submit_challenge(A1 if team is Team.A else B1, team, numbers, argument, self.now)

    def rule(self, winner: Team | None, rulings: dict[Team, bool] | None = None, fill_seconds: float = 40.0) -> None:
        self.game.rule(JUDGE, self.now, winner, {Team.A: all_marks(), Team.B: all_marks(False)}, rulings, fill_seconds)

    def claim(self, team: Team, text: str | None = None) -> None:
        self.game.submit_claim(A1 if team is Team.A else B1, team, text or f"Опора {team.value} раунда {self.game.round.index}", self.now)

    def move(self, team: Team, move: Move) -> None:
        self.game.choose_move(A1 if team is Team.A else B1, team, move, self.now)

    def summary(self) -> None:
        self.game.publish_summary(PRESS, "Заголовок", "Сводка журналиста.", self.now)

    def debrief_all(self) -> None:
        for p in self.game.active_players():
            self.game.submit_debrief_note(p.id, "opora", "level", self.now)

    # ----- типовой раунд -----

    def play_round(self, winner: Team | None, move: Move | None = None) -> None:
        """Полный раунд без вызовов: все действуют вовремя, судья называет победителя."""
        g = self.game
        self.ready()
        self.statement(Team.A)
        self.statement(Team.B)
        self.response(Team.A)
        self.response(Team.B)
        self.rule(winner)
        if winner is not None and move is not None and g.round.move_required(g._ctx()):
            self.move(winner, move)
        self.claim(Team.A)
        self.claim(Team.B)
        if self.phase is Phase.SUMMARY:
            self.summary()


