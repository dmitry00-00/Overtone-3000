# «Окно» для BotHost: одна точка сборки в корне репозитория.
#
# BotHost монтирует исходники из Git в /app при запуске, поэтому приложение
# живёт в /srv/okno, а /app/data — постоянное хранилище платформы: там данные
# встроенного Postgres. Внешнюю базу можно подключить переменной DATABASE_URL
# (или OKNO_DSN) — тогда встроенный Postgres не запускается.

# ---------- 1. сборка Mini App ----------
FROM node:22-slim AS webapp
WORKDIR /build
COPY okno/webapp/package.json okno/webapp/package-lock.json ./
RUN npm ci
COPY okno/webapp/ ./
RUN npm run build

# ---------- 2. рантайм: Python + Postgres ----------
FROM python:3.12-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends postgresql postgresql-contrib \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/okno
COPY okno/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY okno/src/ src/
COPY okno/migrations/ migrations/
COPY okno-decks.md .
COPY --from=webapp /build/dist/ webapp/dist/
COPY deploy/entrypoint.sh /usr/local/bin/okno-entrypoint
RUN chmod +x /usr/local/bin/okno-entrypoint

ENV PYTHONPATH=/srv/okno/src \
    PYTHONUNBUFFERED=1 \
    OKNO_HOST=0.0.0.0 \
    OKNO_DECKS_PATH=/srv/okno/okno-decks.md \
    OKNO_DATA_DIR=/app/data

EXPOSE 8080
CMD ["/usr/local/bin/okno-entrypoint"]
