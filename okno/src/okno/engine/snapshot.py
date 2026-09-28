"""Снимок состояния партии в JSON-совместимый вид: для сравнения в тестах и для API."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

EXCLUDED_GAME_FIELDS = ("dealer", "summary_fallback")


def to_jsonable(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {
            f.name: to_jsonable(getattr(obj, f.name))
            for f in dataclasses.fields(obj)
            if f.name not in EXCLUDED_GAME_FIELDS
        }
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, datetime):
        return obj.astimezone(UTC).isoformat()
    if isinstance(obj, timedelta):
        return obj.total_seconds()
    if isinstance(obj, dict):
        return {to_jsonable(k) if isinstance(k, Enum) else str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (set, frozenset)):
        return sorted(to_jsonable(v) for v in obj)
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, float):
        return round(obj, 6)
    return obj
