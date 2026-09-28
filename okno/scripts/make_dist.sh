#!/bin/sh
# Сборка дистрибутива для хостинга: фронтенд + бэкенд + колоды + Docker-файлы.
# Запуск: sh scripts/make_dist.sh  → okno-dist-ГГГГММДД.tar.gz рядом с проектом.
set -eu
cd "$(dirname "$0")/.."

echo "== сборка Mini App =="
(cd webapp && npm run build)

echo "== проверка колоды =="
.venv/bin/python -c "from okno.decks import load_decks; d = load_decks(); print('карт:', len(d.projects), len(d.carriers), len(d.frames), len(d.circumstances), len(d.audiences))"

STAMP=$(date +%Y%m%d)
OUT="../okno-dist-$STAMP.tar.gz"
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT

mkdir -p "$STAGE/okno"
cp -R src migrations requirements.txt Dockerfile .dockerignore docker-compose.yml .env.example DEPLOY.md "$STAGE/okno/"
mkdir -p "$STAGE/okno/webapp"
cp -R webapp/dist "$STAGE/okno/webapp/dist"
cp ../okno-decks.md "$STAGE/okno/"   # реестр колод едет внутри дистрибутива
find "$STAGE" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
rm -rf "$STAGE/okno/src/okno.egg-info"
find "$STAGE" -name '.DS_Store' -delete 2>/dev/null || true

tar -czf "$OUT" -C "$STAGE" okno
echo "== готово: $(cd .. && pwd)/$(basename "$OUT") =="
tar -tzf "$OUT" | head -12
echo "…"
du -h "$OUT" | cut -f1
