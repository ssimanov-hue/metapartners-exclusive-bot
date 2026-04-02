# Metapartners exclusive Telegram bot

## Запуск

1. Папка проекта: `personal/metapartners-exclusive-bot/` (команды ниже — **из неё**).
2. Зависимости: `pip install -r requirements.txt`
3. Скопируйте [`.env.example`](.env.example) в `.env` и укажите **`BOT_TOKEN`** (от [@BotFather](https://t.me/BotFather)).
4. Запуск polling: `python -m bot`, [`start.py`](start.py) или двойной щелчок по [`run.cmd`](run.cmd). `start.py` / `run.cmd` сами переходят в папку проекта и подключают пакет `bot` **без второго процесса** (надёжнее на Windows). В `run.cmd` включены UTF-8 и `PYTHONPATH`. **Cursor не нужен**. Свёрнутое окно: [`run-minimized.cmd`](run-minimized.cmd). Проверка: [`diagnose.cmd`](diagnose.cmd) или `python -m bot --doctor`.

Без токена команда `python -m bot` завершится с подсказкой. Проверка источников без Telegram:

```text
python -m bot --smoke-sources
```

Если бот «не работает», из папки проекта выполните `python -m bot --doctor` — проверит `.env`, токен и ответ Telegram (без polling).

**Важно:** команды работают **только в личке с ботом**, не в группе. При `/start` в группе бот ответит подсказкой.

При запуске пишется лог **`bot_run.log`** в корне проекта (ошибки и конфликт `getUpdates`). Если окно консоли сразу закрывается — запустите [`run-with-pause.cmd`](run-with-pause.cmd).

## Команды в личке

- `/start` — справка  
- `/today` — эксклюзивы за сегодня (**календарный день и сутки по Europe/Moscow**)  
- `/yesterday` — за вчера по Москве  
- `/day 2026-03-29` — за дату `ГГГГ-ММ-ДД` (границы суток по `DEFAULT_TZ`)

Ответы в HTML, длинные списки режутся по лимиту Telegram (4096 символов). В конце может быть строка «Нет ответа от: …» для изданий, с которых не пришёл ответ.

## Переменные `.env`

| Переменная | Описание |
|------------|----------|
| `BOT_TOKEN` | Обязательно для `python -m bot` |
| `DEFAULT_TZ` | Для `/day`: границы суток (по умолчанию `Europe/Moscow`). `/today` и `/yesterday` всегда по Москве |
| `HTTP_USER_AGENT` | Опционально для HTTP-клиента |
| RT | Короткие эксклюзивы — только карточки с пометкой «Эксклюзив RT» на [russian.rt.com/sport/news](https://russian.rt.com/sport/news); длинные — `/sport/article/` (архив дня, хаб, RSS) |

Файл `.env` не коммитить.

## Если «No module named bot»

Текущая директория должна быть **родительской** для пакета `bot`. Не запускайте `python -m bot` из корня всего workspace — только из этой папки или через `run.cmd`.
