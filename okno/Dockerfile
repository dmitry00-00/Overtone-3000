# «Окно»: API + планировщик + бот + Mini App одним процессом.
# Фронтенд собирается заранее (webapp/dist в дистрибутиве), Node в образе не нужен.
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY migrations/ migrations/
COPY webapp/dist/ webapp/dist/
COPY okno-decks.md .

ENV PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    OKNO_HOST=0.0.0.0 \
    OKNO_PORT=8010

EXPOSE 8010
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"OKNO_PORT\",\"8010\")}/api/health')"

CMD ["python", "-m", "okno.api.app"]
