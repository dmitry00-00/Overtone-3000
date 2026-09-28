"""Postgres: миграции и репозиторий партии."""

from .migrate import migrate
from .repo import Repository

__all__ = ["Repository", "migrate"]
