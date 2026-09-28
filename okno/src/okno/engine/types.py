"""Типы автомата: перечисления, конфиг, записи, ошибки."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum


class IllegalAction(Exception):
    """Действие невозможно в текущем состоянии. Не ошибка программы — отказ автомата."""


class Team(StrEnum):
    A = "team_a"
    B = "team_b"

    @property
    def other(self) -> "Team":
        return Team.B if self is Team.A else Team.A


class Role(StrEnum):
    TEAM_A = "team_a"
    TEAM_B = "team_b"
    JUDGE = "judge"
    JOURNALIST = "journalist"

    @property
    def team(self) -> Team | None:
        if self is Role.TEAM_A:
            return Team.A
        if self is Role.TEAM_B:
            return Team.B
        return None


class Phase(StrEnum):
    """Фазы раунда. OPENING и REVEAL мгновенные: автомат проходит их без ожидания."""

    OPENING = "opening"
    PREP = "prep"
    STATEMENT = "statement"
    REVEAL = "reveal"
    RESPONSE = "response"
    VERDICT = "verdict"
    LEDGER = "ledger"
    SUMMARY = "summary"
    CLOSED = "closed"


TIMED_PHASES = (
    Phase.PREP,
    Phase.STATEMENT,
    Phase.RESPONSE,
    Phase.VERDICT,
    Phase.LEDGER,
    Phase.SUMMARY,
)


class GameStatus(StrEnum):
    LOBBY = "lobby"
    IN_PROGRESS = "in_progress"
    DEBRIEF = "debrief"
    COMPLETED = "completed"  # разбор завершён, партия засчитана
    UNCOUNTED = "uncounted"  # разбор не состоялся, партия закрыта и не засчитана


class Move(StrEnum):
    ADVANCE = "advance"  # шаг себе
    PUSH_BACK = "push_back"  # откат сопернику


class MarkCode(StrEnum):
    """Пять структурных отметок судьи. Хранятся отдельно от счёта партии, никогда не суммируются."""

    OPORA = "opora"  # назвал опору
    STEELMAN = "steelman"  # усилил чужое
    LEVEL = "level"  # нашёл уровень
    LEDGER = "ledger"  # выдержал реестр
    CONDITION = "condition"  # назвал условие


class AporiaReason(StrEnum):
    NO_STATEMENTS = "no_statements"  # обе команды не сдали выступление
    NO_VERDICT = "no_verdict"  # судья не вынес вердикт
    JUDGE_RULED_NOBODY = "judge_ruled_nobody"  # судья сказал «не убедил никто»
    NO_CONSENSUS = "no_consensus"  # взаимный вердикт: команды не сошлись, окно не двинулось
    TECHNICAL = "technical"  # у команды не осталось активных игроков
    TIE = "tie"  # партия закончилась ничем


class TrackCause(StrEnum):
    """Почему фишка сдвинулась. Материал для проигрыша трека в разборе."""

    EXCHANGE_WON = "exchange_won"
    PUSHED_BACK = "pushed_back"
    CHALLENGE_UPHELD = "challenge_upheld"
    CHALLENGE_REJECTED = "challenge_rejected"
    RETRACTION = "retraction"
    STREAK_PROGRESS = "streak_progress"  # первая из двух побед, нужных для 0 → 1


@dataclass(frozen=True)
class Config:
    """Единственный временной параметр — длительность раунда. Окна фаз — доли от неё."""

    rounds: int = 7
    round_duration: timedelta = timedelta(hours=26)
    phase_shares: dict[Phase, float] = field(
        default_factory=lambda: {
            Phase.PREP: 10,
            Phase.STATEMENT: 4,
            Phase.RESPONSE: 4,
            Phase.VERDICT: 4,
            Phase.LEDGER: 2,
            Phase.SUMMARY: 2,
        }
    )
    debrief_window: timedelta = timedelta(days=7)
    end_on_norm: bool = True  # партия завершается досрочно, если фишка дошла до 5
    scoring: str = "delta"  # кто провёл проект дальше: "delta" — от старта, "absolute" — по позиции
    # Кто выносит вердикт. "judge" — классика с судьёй (только она отдаёт данные в профиль);
    # "self" — соло-тренировка: игрок судит свой обмен сам; "mutual" — дуэль без судьи:
    # обе команды голосуют, согласие даёт вердикт, несогласие — апорию.
    judging: str = "judge"
    claim_max_words: int = 15
    track_size: int = 6  # позиции 0..5

    def phase_window(self, phase: Phase) -> timedelta:
        total = sum(self.phase_shares.values())
        return self.round_duration * (self.phase_shares[phase] / total)


# ---------- записи (то, что позже ляжет в таблицы) ----------


@dataclass
class Player:
    id: str
    role: Role
    display_name: str = ""
    dropped_at: datetime | None = None

    @property
    def active(self) -> bool:
        return self.dropped_at is None

    @property
    def is_ai(self) -> bool:
        """ИИ-место (соперник в соло). Не судит, не участвует в разборе."""
        return self.id.startswith("ai:")


@dataclass(frozen=True)
class Deal:
    """Результат OPENING: обстоятельство, руки команд, карта публики."""

    circumstance_code: str
    audience_code: str
    hands: dict[Team, tuple[str, str]]  # team -> (carrier_code, frame_code)


@dataclass
class Statement:
    team: Team
    body: str
    author_id: str
    submitted_at: datetime
    prep_seconds: float
    edit_count: int = 0


@dataclass
class Response:
    team: Team
    body: str
    submitted_at: datetime


@dataclass
class Challenge:
    team: Team  # кто вызывает
    claim_numbers: tuple[int, ...]  # номера заявлений соперника
    argument: str
    submitted_at: datetime
    upheld: bool | None = None  # None — судья не вынес решения
    ruled_at: datetime | None = None


@dataclass
class Verdict:
    winner: Team | None
    is_aporia: bool
    aporia_reason: AporiaReason | None
    judge_id: str | None
    ruled_at: datetime
    by_forfeit: bool = False
    fill_seconds: float | None = None
    move: Move | None = None  # выбор победителя; заполняется в LEDGER


@dataclass
class VerdictVote:
    """Голос команды во взаимном вердикте: кто убедил и отметки карточки соперника."""

    team: Team
    winner: Team | None  # None — «не убедил никто»
    opponent_marks: dict[MarkCode, bool]
    submitted_at: datetime
    challenge_concede: bool | None = None  # ответ на вызов соперника: признать противоречие


@dataclass
class Marks:
    team: Team
    values: dict[MarkCode, bool]
    judge_id: str
    draft: dict[MarkCode, bool] | None = None  # предзаполнение ИИ (Фаза 2); в профиль идёт values


@dataclass
class LedgerClaim:
    team: Team
    round_index: int
    number: int  # сквозной в пределах команды; после отзыва не переиспользуется
    text: str
    weak: bool = False  # «команда не сформулировала опору»
    retracted_at: datetime | None = None
    retracted_in_round: int | None = None
    challenged_in_round: int | None = None  # засчитанный вызов, в котором фигурировало

    @property
    def retracted(self) -> bool:
        return self.retracted_at is not None


@dataclass
class Summary:
    headline: str
    body: str
    author: str  # "journalist" | "ai" | "system"
    published_at: datetime


@dataclass(frozen=True)
class TrackEvent:
    round_index: int
    team: Team
    position_from: int
    position_to: int
    cause: TrackCause
    at: datetime


@dataclass(frozen=True)
class StructuralEvent:
    """Плюсы прибора, идущие мимо карточки судьи. Пока один: отзыв заявления."""

    round_index: int
    team: Team
    player_id: str
    atom: str
    at: datetime


@dataclass
class DebriefNote:
    player_id: str
    atom_worked: str
    atom_missed: str
    at: datetime


@dataclass(frozen=True)
class GameOutcome:
    winner: Team | None
    is_aporia: bool
    aporia_reason: AporiaReason | None
    positions: dict[Team, int]
    deltas: dict[Team, int]
