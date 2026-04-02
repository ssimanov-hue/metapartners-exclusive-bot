"""
Запуск на Fly.io: слушаем PORT (health), затем тот же цикл событий — Telegram polling.

Локально: `python -m bot` по-прежнему основной вход.
"""

from __future__ import annotations

import asyncio
import os

from aiohttp import web


async def main() -> None:
    port = int(os.environ.get("PORT", "8080"))

    app = web.Application()
    app.router.add_get("/", lambda _r: web.Response(text="ok"))

    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", port).start()

    from bot.main import run_polling

    await run_polling()


if __name__ == "__main__":
    asyncio.run(main())
