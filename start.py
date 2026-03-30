"""
Запуск бота из любой текущей папки терминала.

Пример (из корня workspace):
  python personal/metapartners-exclusive-bot/start.py

Или двойной щелчок по start.py / run.cmd в папке проекта.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> None:
    r = subprocess.run(
        [sys.executable, "-m", "bot"],
        cwd=str(ROOT),
    )
    raise SystemExit(r.returncode)


if __name__ == "__main__":
    main()
