# Metapartners exclusive Telegram bot

## Запуск

1. Папка проекта: `personal/metapartners-exclusive-bot/` (команды ниже — **из неё**).
2. Зависимости: `pip install -r requirements.txt`
3. Скопируйте [`.env.example`](.env.example) в `.env` и укажите **`BOT_TOKEN`** (от [@BotFather](https://t.me/BotFather)).
4. Запуск polling: `python -m bot` или двойной щелчок по [`run.cmd`](run.cmd) (ставит `PYTHONPATH` сам).

Без токена команда `python -m bot` завершится с подсказкой. Проверка источников без Telegram:

```text
python -m bot --smoke-sources
```

## Команды в личке

- `/start` — справка  
- `/today` — эксклюзивы за сегодня (календарный день в `DEFAULT_TZ`)  
- `/yesterday` — за вчера  
- `/day 2026-03-29` — за дату `ГГГГ-ММ-ДД`

Ответы в HTML, длинные списки режутся по лимиту Telegram (4096 символов). В конце может быть строка «Нет ответа от: …» для изданий, с которых не пришёл ответ.

## Переменные `.env`

| Переменная | Описание |
|------------|----------|
| `BOT_TOKEN` | Обязательно для `python -m bot` |
| `DEFAULT_TZ` | По умолчанию `Europe/Moscow` |
| `HTTP_USER_AGENT` | Опционально для HTTP-клиента |
| RT | Берётся архив `russian.rt.com/sport/news/ГГГГ-ММ-ДД/` за запрошенный день |

Файл `.env` не коммитить.

## Если «No module named bot»

Текущая директория должна быть **родительской** для пакета `bot`. Не запускайте `python -m bot` из корня всего workspace — только из этой папки или через `run.cmd`.
