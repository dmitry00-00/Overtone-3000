"""Импорт реестров колод из ``okno-decks.md``.

Файл реестра — единственный источник содержимого карт для обеих версий игры,
поэтому он читается как есть, без промежуточного JSON.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from pathlib import Path

from .engine.types import Deal, Team

def default_decks_path() -> Path:
    """Где лежит реестр: переменная OKNO_DECKS_PATH, корень проекта (дистрибутив),
    родительская папка проекта (рабочая копия рядом с ТЗ)."""
    import os

    env = os.environ.get("OKNO_DECKS_PATH")
    candidates = [Path(env)] if env else []
    root = Path(__file__).resolve().parents[2]
    candidates += [root / "okno-decks.md", root.parent / "okno-decks.md"]
    for c in candidates:
        if c.exists():
            return c
    raise FileNotFoundError(f"okno-decks.md не найден; искал: {', '.join(map(str, candidates))}")


@dataclass(frozen=True)
class Project:
    code: str
    title: str
    start: int
    objections: tuple[str, str]


@dataclass(frozen=True)
class Carrier:
    code: str
    title: str
    benefit: str
    danger: str


@dataclass(frozen=True)
class Frame:
    code: str
    title: str
    to_prove: str
    trap: str


@dataclass(frozen=True)
class Circumstance:
    code: str
    event: str
    changes: str


@dataclass(frozen=True)
class Audience:
    code: str
    mood: str
    accepts: str
    rejects: str


@dataclass
class Decks:
    projects: dict[str, Project] = field(default_factory=dict)
    carriers: dict[str, Carrier] = field(default_factory=dict)
    frames: dict[str, Frame] = field(default_factory=dict)
    circumstances: dict[str, Circumstance] = field(default_factory=dict)
    audiences: dict[str, Audience] = field(default_factory=dict)

    def projects_by_start(self) -> dict[int, list[Project]]:
        out: dict[int, list[Project]] = {}
        for p in self.projects.values():
            out.setdefault(p.start, []).append(p)
        return out


_PROJECT_HEAD = re.compile(r"^\*\*(П-\d+)\.\s+(.+?)\*\*\s*$")
_START_HEAD = re.compile(r"^### Старт (\d) ")
_ROW = re.compile(r"^\|\s*([А-Яа-я]+-\d+)\s*\|(.*)\|\s*$")


def _cells(rest: str) -> list[str]:
    return [c.strip() for c in rest.split("|")]


def parse_decks(text: str) -> Decks:
    decks = Decks()
    start: int | None = None
    pending: Project | None = None
    for line in text.splitlines():
        m = _START_HEAD.match(line)
        if m:
            start = int(m.group(1))
            continue
        m = _PROJECT_HEAD.match(line)
        if m and start is not None:
            pending = Project(m.group(1), m.group(2), start, ("", ""))
            continue
        if pending is not None and line.startswith("Возражения:"):
            parts = [s.strip().rstrip(".") for s in line.removeprefix("Возражения:").split(";")]
            if len(parts) != 2:
                raise ValueError(f"{pending.code}: ожидались два возражения через «;»")
            decks.projects[pending.code] = Project(pending.code, pending.title, pending.start, (parts[0], parts[1]))
            pending = None
            continue
        m = _ROW.match(line)
        if not m:
            continue
        code, cells = m.group(1), _cells(m.group(2))
        prefix = code.split("-")[0]
        match prefix, len(cells):
            case "Н", 3:
                decks.carriers[code] = Carrier(code, *cells)
            case "Р", 3:
                decks.frames[code] = Frame(code, *cells)
            case "О", 2:
                decks.circumstances[code] = Circumstance(code, *cells)
            case "Пб", 3:
                decks.audiences[code] = Audience(code, *cells)
            case _:
                raise ValueError(f"{code}: неожиданное число колонок {len(cells)}")
    return decks


def load_decks(path: Path | None = None) -> Decks:
    return parse_decks(Path(path or default_decks_path()).read_text(encoding="utf-8"))


class DeckDealer:
    """Раздача из колод реестра. Внутри партии карты не повторяются, пока колода не исчерпана.

    ``used_*`` — карты, уже вышедшие в этой партии (при загрузке из БД), они исключаются
    из стопок до первого исчерпания.
    """

    def __init__(
        self,
        decks: Decks,
        seed: int | None = None,
        used_projects: set[str] = frozenset(),
        used_circumstances: set[str] = frozenset(),
        used_carriers: set[str] = frozenset(),
        used_audiences: set[str] = frozenset(),
        used_frames: dict[Team, list[str]] | None = None,
    ):
        self.decks = decks
        self.rng = random.Random(seed)
        self._projects = self._shuffled(decks.projects, used_projects)
        self._circumstances = self._shuffled(decks.circumstances, used_circumstances)
        self._carriers = self._shuffled(decks.carriers, used_carriers)
        self._audiences = self._shuffled(decks.audiences, used_audiences)
        used_frames = used_frames or {}
        # рамок семь, команда проходит колоду и начинает заново: исключаем только текущий проход
        self._frames: dict[Team, list[str]] = {}
        for t in Team:
            seen = used_frames.get(t, [])
            current_pass = seen[len(seen) - len(seen) % len(decks.frames):] if decks.frames else []
            self._frames[t] = self._shuffled(decks.frames, set(current_pass)) if current_pass else []

    def _shuffled(self, cards: dict[str, object], exclude: set[str] = frozenset()) -> list[str]:
        codes = [c for c in cards if c not in exclude]
        self.rng.shuffle(codes)
        return codes

    def _draw(self, pile: list[str], source: dict[str, object]) -> str:
        if not pile:
            pile.extend(self._shuffled(source))
        return pile.pop()

    def deal_projects(self) -> dict[Team, tuple[str, int]]:
        out = {}
        for team in Team:
            code = self._draw(self._projects, self.decks.projects)
            out[team] = (code, self.decks.projects[code].start)
        return out

    def deal_round(self, index: int) -> Deal:
        hands = {}
        for team in Team:
            carrier = self._draw(self._carriers, self.decks.carriers)
            frame = self._draw(self._frames[team], self.decks.frames)
            hands[team] = (carrier, frame)
        return Deal(
            circumstance_code=self._draw(self._circumstances, self.decks.circumstances),
            audience_code=self._draw(self._audiences, self.decks.audiences),
            hands=hands,
        )


class FixedDealer:
    """Детерминированная раздача для тестов и скриптовых прогонов."""

    def __init__(self, starts: dict[Team, int] | None = None):
        self.starts = starts or {Team.A: 1, Team.B: 1}

    def deal_projects(self) -> dict[Team, tuple[str, int]]:
        return {t: (f"П-{i:02d}", s) for i, (t, s) in enumerate(self.starts.items(), start=1)}

    def deal_round(self, index: int) -> Deal:
        return Deal(
            circumstance_code=f"О-{index:02d}",
            audience_code=f"Пб-{index}",
            hands={Team.A: (f"Н-{index:02d}", "Р-1"), Team.B: (f"Н-{index + 12:02d}", "Р-2")},
        )
