"""Применить миграции и импортировать реестры колод.

    OKNO_DSN=postgresql://localhost/okno .venv/bin/python scripts/init_db.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import psycopg

from okno.db import Repository, migrate
from okno.db.migrate import DEFAULT_DSN
from okno.decks import load_decks

if __name__ == "__main__":
    applied = migrate(DEFAULT_DSN)
    print("миграции:", ", ".join(applied) if applied else "актуальны")
    decks = load_decks()
    with psycopg.connect(DEFAULT_DSN) as conn:
        Repository(conn, decks).import_decks()
        counts = {t: conn.execute(f"select count(*) from {t}").fetchone()[0] for t in ("projects", "carriers", "frames", "circumstances", "audiences")}
    print("колоды:", counts)
