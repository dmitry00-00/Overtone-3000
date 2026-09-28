"""Раннер миграций: файлы migrations/NNNN_*.sql применяются по порядку, каждый в своей транзакции."""

from __future__ import annotations

import os
from pathlib import Path

import psycopg

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations"
DEFAULT_DSN = os.environ.get("OKNO_DSN", "postgresql://localhost/okno")


def migrate(dsn: str = DEFAULT_DSN, directory: Path = MIGRATIONS_DIR) -> list[str]:
    """Применить неприменённые миграции. Возвращает имена применённых."""
    applied: list[str] = []
    with psycopg.connect(dsn) as conn:
        conn.execute(
            "create table if not exists schema_migrations (name text primary key, applied_at timestamptz not null default now())"
        )
        done = {r[0] for r in conn.execute("select name from schema_migrations")}
        conn.commit()
        for path in sorted(directory.glob("[0-9]*.sql")):
            if path.name in done:
                continue
            with conn.transaction():
                conn.execute(path.read_text(encoding="utf-8"))
                conn.execute("insert into schema_migrations (name) values (%s)", (path.name,))
            applied.append(path.name)
    return applied


if __name__ == "__main__":
    names = migrate()
    print("применено:", ", ".join(names) if names else "нечего")
