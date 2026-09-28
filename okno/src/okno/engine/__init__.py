"""Автомат раунда и партии. Чистая доменная логика: без БД, без ИИ, без сети."""

from .types import (
    AporiaReason,
    Config,
    GameStatus,
    IllegalAction,
    MarkCode,
    Move,
    Phase,
    Role,
    Team,
)
from .game import Game
from .track import Track

__all__ = [
    "AporiaReason",
    "Config",
    "Game",
    "GameStatus",
    "IllegalAction",
    "MarkCode",
    "Move",
    "Phase",
    "Role",
    "Team",
    "Track",
]
