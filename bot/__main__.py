"""Run: python -m bot  |  python -m bot --smoke-sources"""

from __future__ import annotations

import argparse
import asyncio
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="Metapartners exclusive Telegram bot")
    parser.add_argument(
        "--smoke-sources",
        action="store_true",
        help="Only fetch all sources (no Telegram)",
    )
    args = parser.parse_args()

    if args.smoke_sources:
        from bot.main import load_env
        from bot.sources.registry import _main_sync

        load_env()
        _main_sync()
        return

    from bot.main import run_polling

    asyncio.run(run_polling())


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
