# Деплой на EC2 (Docker, polling)

## Ограничения

- Один активный процесс с тем же `BOT_TOKEN`: **остановите сервис на Railway** перед запуском на EC2, иначе `getUpdates` — конфликт.
- Секреты не коммитить: `.env` только на сервере, `chmod 600 .env`.

## 1. Elastic IP (один раз)

Регион **eu-central-1**: EC2 → Elastic IPs → Allocate → Associate с инстансом `prod-tg-bot-metapartners`. Дальше SSH: `ubuntu@<EIP>`.

## 2. Сервер: Docker

```bash
sudo apt update && sudo apt install -y docker.io docker-compose-v2 git
sudo usermod -aG docker ubuntu
# выйти из SSH и зайти снова
```

## 3. Код и секреты

```bash
cd ~
git clone <URL-репозитория> metapartners-exclusive-bot
cd metapartners-exclusive-bot
nano .env   # BOT_TOKEN, DEFAULT_TZ, HTTP_USER_AGENT — как в Railway
chmod 600 .env
docker compose up -d --build
docker compose logs -f --tail=80
```

Проверка health с инстанса: `curl -sS http://127.0.0.1:8080/` → `ok`.

Проверка в Telegram: личка с ботом → `/start` или `python -m bot --doctor` внутри контейнера:

```bash
docker compose exec bot python -m bot --doctor
```

## 4. Обновление

```bash
cd ~/metapartners-exclusive-bot
git pull
docker compose up -d --build
```
