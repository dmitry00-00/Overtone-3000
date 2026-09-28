import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from okno.sim import A1, A2, B1, B2, JUDGE, PRESS, T0, Sim, all_marks  # noqa: F401 — реэкспорт для тестов


@pytest.fixture
def sim() -> Sim:
    s = Sim()
    s.start()
    return s
