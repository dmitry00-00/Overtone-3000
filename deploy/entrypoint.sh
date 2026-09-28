#!/bin/sh
# Запуск «Окна» в контейнере: встроенный Postgres (если не задана внешняя база) + приложение.
set -eu

DATA_DIR="${OKNO_DATA_DIR:-/app/data}"
PG_BIN="$(ls -d /usr/lib/postgresql/*/bin | tail -1)"

if [ -z "${OKNO_DSN:-}" ] && [ -z "${DATABASE_URL:-}" ]; then
  PGDATA="$DATA_DIR/postgres"
  mkdir -p "$PGDATA" /run/postgresql
  chown -R postgres:postgres "$DATA_DIR/postgres" /run/postgresql
  chmod 700 "$PGDATA"

  if [ ! -s "$PGDATA/PG_VERSION" ]; then
    echo "okno: первая инициализация базы в $PGDATA"
    su postgres -c "$PG_BIN/initdb -D '$PGDATA' --auth=trust --encoding=UTF8 --locale=C.UTF-8" >/dev/null
  fi

  # Слушаем только сокет внутри контейнера — наружу база не торчит.
  su postgres -c "$PG_BIN/pg_ctl -D '$PGDATA' -o \"-c listen_addresses='' -k /run/postgresql\" -w -l '$DATA_DIR/postgres.log' start"
  su postgres -c "psql -h /run/postgresql -tAc \"select 1 from pg_database where datname='okno'\"" | grep -q 1 \
    || su postgres -c "createdb -h /run/postgresql okno"

  export OKNO_DSN="postgresql://postgres@/okno?host=/run/postgresql"
  EMBEDDED_PG=1
fi

stop_pg() {
  if [ "${EMBEDDED_PG:-0}" = 1 ]; then
    su postgres -c "$PG_BIN/pg_ctl -D '$PGDATA' -m fast stop" >/dev/null 2>&1 || true
  fi
}

cd /srv/okno
# Порт даёт платформа через PORT; миграции и импорт колод выполняются при старте приложения.
# Приложение — дочерний процесс: сигнал остановки пересылаем ему, затем гасим базу.
python -m okno.api.app &
APP=$!
trap 'kill -TERM "$APP" 2>/dev/null; wait "$APP"; stop_pg; exit 0' INT TERM
wait "$APP"
CODE=$?
stop_pg
exit "$CODE"
