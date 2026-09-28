"""Планировщик тиков: раз в N секунд проводит через автомат партии с истёкшими дедлайнами.

Живёт как asyncio-задача внутри процесса FastAPI. Один процесс — один планировщик;
блокировка строки games делает повторный тик безопасным.
"""

from __future__ import annotations

import asyncio
import logging

from .service import GameService

log = logging.getLogger("okno.scheduler")


async def run(service: GameService, interval_s: float, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            ticked = await asyncio.to_thread(service.tick_due)
            if ticked:
                log.info("тик: %s", ", ".join(ticked))
        except Exception:  # noqa: BLE001 — планировщик не должен умирать от одной партии
            log.exception("тик упал")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_s)
        except TimeoutError:
            pass
