"""Трек окна: две фишки, шесть позиций, жёсткие границы, серия для шага 0 → 1."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .types import IllegalAction, Move, Team, TrackCause, TrackEvent


@dataclass
class Track:
    size: int = 6
    positions: dict[Team, int] = field(default_factory=lambda: {Team.A: 0, Team.B: 0})
    start: dict[Team, int] = field(default_factory=dict)
    # Серия выигранных обменов подряд. Шаг 0 → 1 требует серии ≥ 2 (включая текущий выигрыш).
    streak: dict[Team, int] = field(default_factory=lambda: {Team.A: 0, Team.B: 0})
    events: list[TrackEvent] = field(default_factory=list)

    @property
    def top(self) -> int:
        return self.size - 1

    def set_start(self, team: Team, position: int) -> None:
        if not 0 <= position <= self.top:
            raise IllegalAction(f"стартовая позиция {position} вне трека")
        self.positions[team] = position
        self.start[team] = position

    # ----- серия -----

    def record_exchange(self, winner: Team | None) -> None:
        """Обновить серии по итогу обмена. Апория (winner=None) прерывает обе серии."""
        for team in Team:
            self.streak[team] = self.streak[team] + 1 if team is winner else 0

    # ----- возможные ходы -----

    def can_advance(self, team: Team) -> bool:
        return self.positions[team] < self.top

    def can_push_back(self, team: Team) -> bool:
        return self.positions[team.other] > 0

    def legal_moves(self, team: Team) -> tuple[Move, ...]:
        moves = []
        if self.can_advance(team):
            moves.append(Move.ADVANCE)
        if self.can_push_back(team):
            moves.append(Move.PUSH_BACK)
        return tuple(moves)

    def default_move(self, team: Team) -> Move | None:
        """Ход по умолчанию, если победитель не выбрал: шаг себе, иначе откат, иначе ничего."""
        moves = self.legal_moves(team)
        return moves[0] if moves else None

    # ----- применение -----

    def apply_move(self, winner: Team, move: Move, round_index: int, at: datetime) -> None:
        """Ход победителя обмена. Серия уже должна быть обновлена через record_exchange."""
        if move is Move.ADVANCE:
            self.advance(winner, round_index, at, TrackCause.EXCHANGE_WON)
        elif move is Move.PUSH_BACK:
            self.push_back(winner.other, round_index, at, TrackCause.PUSHED_BACK)
        else:
            raise IllegalAction(f"неизвестный ход {move}")

    def advance(self, team: Team, round_index: int, at: datetime, cause: TrackCause) -> bool:
        """Шаг вперёд. Возвращает True, если фишка сдвинулась.

        Из 0 фишка выходит только на второй победе подряд: первая записывается
        как STREAK_PROGRESS без сдвига.
        """
        pos = self.positions[team]
        if pos >= self.top:
            return False
        if pos == 0 and self.streak[team] < 2:
            self.events.append(TrackEvent(round_index, team, 0, 0, TrackCause.STREAK_PROGRESS, at))
            return False
        self.positions[team] = pos + 1
        self.events.append(TrackEvent(round_index, team, pos, pos + 1, cause, at))
        return True

    def push_back(self, team: Team, round_index: int, at: datetime, cause: TrackCause) -> bool:
        pos = self.positions[team]
        if pos <= 0:
            return False
        self.positions[team] = pos - 1
        self.events.append(TrackEvent(round_index, team, pos, pos - 1, cause, at))
        return True

    def reached_norm(self) -> Team | None:
        for team in Team:
            if self.positions[team] >= self.top:
                return team
        return None

    def delta(self, team: Team) -> int:
        return self.positions[team] - self.start.get(team, 0)
