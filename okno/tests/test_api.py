"""Полный раунд через HTTP в dev-режиме авторизации. Нужен Postgres (okno_test)."""

from __future__ import annotations

import os
import time

import pytest

psycopg = pytest.importorskip("psycopg")
from fastapi.testclient import TestClient  # noqa: E402

DSN = os.environ.get("OKNO_TEST_DSN", "postgresql://localhost/okno_test")


@pytest.fixture(scope="module")
def client():
    from okno.api.app import create_app
    from okno.api.settings import Settings

    try:
        psycopg.connect(DSN).close()
    except psycopg.OperationalError as e:  # pragma: no cover
        pytest.skip(f"Postgres недоступен: {e}")
    app = create_app(Settings(dsn=DSN, bot_token=None, dev_auth=True), run_scheduler=False)
    with TestClient(app) as c:
        yield c


def as_(uid: str, name: str = "") -> dict:
    from urllib.parse import quote

    return {"X-Dev-User": f"{uid}:{quote(name or uid)}"}


A1, A2, B1, JUDGE, PRESS = as_("a1", "Аня"), as_("a2", "Артём"), as_("b1", "Борис"), as_("judge", "Судья"), as_("press", "Пресса")


def _new_game(client, **body) -> str:
    r = client.post("/api/games", json={"role": "team_a", **body}, headers=A1)
    assert r.status_code == 200, r.text
    gid = r.json()["game"]["id"]
    for h, role in ((A2, "team_a"), (B1, "team_b"), (JUDGE, "judge"), (PRESS, "journalist")):
        assert client.post(f"/api/games/{gid}/join", json={"role": role}, headers=h).status_code == 200
    return gid


def test_unauthorized():
    from okno.api.app import create_app
    from okno.api.settings import Settings

    app = create_app(Settings(dsn=DSN, bot_token=None, dev_auth=True), run_scheduler=False)
    with TestClient(app) as c:
        assert c.get("/api/me").status_code == 401


def test_lobby_and_full_round(client):
    gid = _new_game(client)
    v = client.get(f"/api/games/{gid}", headers=A1).json()
    assert v["prompt"]["kind"] == "lobby" and len(v["players"]) == 5
    assert v["projects"]["team_a"]["title"]

    # старт: судья не может выступать, команда получает подсказку
    assert client.post(f"/api/games/{gid}/start", headers=JUDGE).status_code == 200
    v = client.get(f"/api/games/{gid}", headers=A1).json()
    assert v["prompt"]["kind"] == "prep" and v["round"]["phase"] == "prep"
    assert v["round"]["audience"] is None  # публику видит судья
    assert client.get(f"/api/games/{gid}", headers=JUDGE).json()["round"]["audience"]["mood"]
    assert client.post(f"/api/games/{gid}/statement", json={"body": "x"}, headers=JUDGE).status_code == 403

    client.post(f"/api/games/{gid}/ready", headers=A2)
    client.post(f"/api/games/{gid}/ready", headers=B1)
    # слепая сдача: пока B не сдала, A не видит ничего чужого, B не видит A
    client.post(f"/api/games/{gid}/statement", json={"body": "Выступление A"}, headers=A1)
    vb = client.get(f"/api/games/{gid}", headers=B1).json()
    assert "team_a" not in vb["round"]["statements"] and vb["prompt"]["kind"] == "statement"
    client.post(f"/api/games/{gid}/statement", json={"body": "Выступление B"}, headers=B1)
    va = client.get(f"/api/games/{gid}", headers=A1).json()
    assert va["round"]["statements"]["team_b"]["body"] == "Выступление B" and va["round"]["phase"] == "response"

    client.post(f"/api/games/{gid}/response", json={"body": "Реплика A"}, headers=A1)
    client.post(f"/api/games/{gid}/response", json={"body": "Реплика B"}, headers=B1)
    # действие не в свою фазу — 409, а не 500
    assert client.post(f"/api/games/{gid}/statement", json={"body": "поздно"}, headers=A1).status_code == 409

    marks = {code: True for code in ("opora", "steelman", "level", "ledger", "condition")}
    r = client.post(
        f"/api/games/{gid}/rule",
        json={"winner": "team_a", "marks": {"team_a": marks, "team_b": {**marks, "level": False}}, "fill_seconds": 48},
        headers=JUDGE,
    )
    assert r.status_code == 200, r.text
    va = client.get(f"/api/games/{gid}", headers=A1).json()
    assert va["prompt"]["kind"] == "ledger"
    assert "team_b" not in va["round"]["marks"]  # чужие отметки до разбора не видны
    if va["track"]["positions"]["team_b"] > 0:  # соперника есть куда откатывать — выбор нужен
        assert set(va["legal_moves"]) == {"advance", "push_back"}
        client.post(f"/api/games/{gid}/move", json={"move": "advance"}, headers=A1)
    else:
        assert va["legal_moves"] == []  # единственный ход применится сам
    client.post(f"/api/games/{gid}/claim", json={"body": "Опора A"}, headers=A1)
    assert client.post(f"/api/games/{gid}/claim", json={"body": " ".join(["слово"] * 16)}, headers=B1).status_code == 409
    client.post(f"/api/games/{gid}/claim", json={"body": "Опора B"}, headers=B1)
    vp = client.get(f"/api/games/{gid}", headers=PRESS).json()
    assert vp["prompt"]["kind"] == "summary"
    client.post(f"/api/games/{gid}/summary", json={"headline": "Заголовок", "body": "Сводка"}, headers=PRESS)

    v = client.get(f"/api/games/{gid}", headers=A1).json()
    assert v["round"]["index"] == 2 and len(v["rounds"]) == 1
    assert v["track"]["positions"]["team_a"] == v["track"]["start"]["team_a"] + (1 if v["track"]["start"]["team_a"] > 0 else 0)
    assert [c["number"] for c in v["ledger"]] == [1, 1]
    assert v["rounds"][0]["summary"]["author"] == "journalist"

    me = client.get("/api/me", headers=A1).json()
    assert any(g["id"] == gid and g["round_index"] == 2 for g in me["games"])


def test_tick_moves_expired_phase(client):
    gid = _new_game(client, round_hours=0.002)  # раунд 7.2 с: PREP ≈ 2.8 с, STATEMENT ≈ 1.1 с
    client.post(f"/api/games/{gid}/start", headers=A1)
    time.sleep(3.0)
    ticked = client.post("/api/tick").json()["ticked"]
    assert gid in ticked
    v = client.get(f"/api/games/{gid}", headers=A1).json()
    assert v["round"]["phase"] == "statement"
    assert v["round"]["transitions"][-1]["by_timeout"]
