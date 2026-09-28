"""Сборка приложения. ``uvicorn --factory okno.api.app:create_app`` или ``python -m okno.api.app``."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from psycopg_pool import ConnectionPool

from ..db.migrate import migrate
from ..decks import load_decks
from . import scheduler
from .routes import router
from .service import GameService
from .settings import Settings

WEBAPP_DIST = Path(__file__).resolve().parents[3] / "webapp" / "dist"


def _load_dotenv() -> None:
    """Минимальный .env без зависимостей: только KEY=VALUE, уже заданное окружение не трогаем."""
    path = Path(__file__).resolve().parents[3] / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"'))


def create_app(settings: Settings | None = None, run_scheduler: bool = True) -> FastAPI:
    _load_dotenv()
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        migrate(settings.dsn)
        pool = ConnectionPool(settings.dsn, min_size=1, max_size=8, open=True)
        decks = load_decks()
        # Свежая база на хостинге заполняется сама: upsert справочников идемпотентен.
        from ..db.repo import Repository

        with pool.connection() as conn:
            Repository(conn, decks).import_decks()
        app.state.settings = settings
        app.state.service = GameService(pool, decks)
        stop = asyncio.Event()
        tasks = []
        if run_scheduler:
            tasks.append(asyncio.create_task(scheduler.run(app.state.service, settings.tick_interval_s, stop)))
        if run_scheduler and settings.run_bot and settings.bot_token:
            from ..bot.main import OknoBot

            bot = OknoBot(settings.bot_token, app.state.service, settings.webapp_url, settings.app_short_name)
            tasks.append(asyncio.create_task(bot.run(stop)))
        else:
            logging.getLogger("okno").info("бот не запущен: нет OKNO_BOT_TOKEN")
        try:
            yield
        finally:
            stop.set()
            await asyncio.gather(*tasks, return_exceptions=True)
            pool.close()

    app = FastAPI(title="Окно", lifespan=lifespan)
    app.include_router(router)
    if WEBAPP_DIST.exists():
        app.mount("/", StaticFiles(directory=WEBAPP_DIST, html=True), name="webapp")
    return app


if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    _load_dotenv()
    uvicorn.run(
        "okno.api.app:create_app",
        factory=True,
        host=os.environ.get("OKNO_HOST", "127.0.0.1"),
        port=int(os.environ.get("OKNO_PORT") or os.environ.get("PORT") or "8010"),
    )
