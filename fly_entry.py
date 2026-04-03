"""
Облако (Fly.io, Railway): слушаем PORT (health «/»), затем тот же цикл — Telegram polling.

Локально основной вход: `python -m bot`.
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
