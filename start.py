"""
Запуск бота из любой текущей папки терминала.

Двойной щелчок по start.py / run.cmd — тот же код, что и «python -m bot»,
без отдельного дочернего процесса (меньше проблем с PATH и PYTHONPATH на Windows).

Пример из корня workspace:
  python personal/metapartners-exclusive-bot/start.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> None:
    root_s = str(ROOT)
    os.chdir(root_s)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)
    if sys.platform == "win32":
        os.environ.setdefault("PYTHONUTF8", "1")

    from bot.__main__ import main as bot_main

    bot_main()


if __name__ == "__main__":
    main()
