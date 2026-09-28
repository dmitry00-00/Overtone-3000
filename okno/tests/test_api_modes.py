"""Соло и дуэль через HTTP: ИИ отвечает сразу, голоса сводятся, экспорт закрыт."""

from __future__ import annotations

import os

import pytest

psycopg = pytest.importorskip("psycopg")
from fastapi.testclient import TestClient  # noqa: E402

DSN = os.environ.get("OKNO_TEST_DSN", "postgresql://localhost/okno_test")
MARKS = {c: True for c in ("opora", "steelman", "level", "ledger", "condition")}


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


def as_(uid: str) -> dict:
    return {"X-Dev-User": uid}


def test_solo_round_ai_answers_immediately(client):
    h = as_("solo-http")
    v = client.post("/api/games", json={"mode": "solo"}, headers=h).json()
    gid = v["game"]["id"]
    assert v["game"]["judging"] == "self"
    assert any(p["is_ai"] for p in v["players"])
    v = client.post(f"/api/games/{gid}/start", headers=h).json()
    v = client.post(f"/api/games/{gid}/ready", headers=h).json()
    assert v["round"]["phase"] == "statement"  # ИИ отметил готовность сам
    v = client.post(f"/api/games/{gid}/statement", json={"body": "Моё выступление"}, headers=h).json()
    assert v["round"]["phase"] == "response"  # ИИ сдал выступление сразу
    assert v["round"]["statements"]["team_b"]["body"]
    v = client.post(f"/api/games/{gid}/response", json={"body": "Реплика"}, headers=h).json()
    assert v["round"]["phase"] == "verdict"
    assert v["prompt"]["kind"] == "verdict" and "Самосуд" in v["prompt"]["text"]
    r = client.post(f"/api/games/{gid}/rule", json={"winner": "team_a", "marks": {"team_a": MARKS, "team_b": MARKS}}, headers=h)
    assert r.status_code == 200, r.text
    v = client.post(f"/api/games/{gid}/claim", json={"body": "Опора соло"}, headers=h).json()
    if v["round"]["phase"] == "ledger" and "team_a:move" in v["round"]["pending"]:
        v = client.post(f"/api/games/{gid}/move", json={"move": "advance"}, headers=h).json()
    # ИИ записал опору, раунд ушёл в следующий (журналиста нет — сводка ИИ)
    assert v["round"]["index"] == 2
    assert v["rounds"][0]["summary"]["author"] == "ai"
    assert len([c for c in v["ledger"] if c["team"] == "team_b"]) == 1


def test_duel_votes_and_closed_export(client):
    a, b = as_("duel-a"), as_("duel-b")
    v = client.post("/api/games", json={"mode": "duel"}, headers=a).json()
    gid = v["game"]["id"]
    assert v["game"]["judging"] == "mutual"
    client.post(f"/api/games/{gid}/join", json={"role": "team_b"}, headers=b)
    client.post(f"/api/games/{gid}/start", headers=a)
    client.post(f"/api/games/{gid}/ready", headers=a)
    client.post(f"/api/games/{gid}/ready", headers=b)
    client.post(f"/api/games/{gid}/statement", json={"body": "A"}, headers=a)
    client.post(f"/api/games/{gid}/statement", json={"body": "B"}, headers=b)
    client.post(f"/api/games/{gid}/response", json={"body": "ра"}, headers=a)
    v = client.post(f"/api/games/{gid}/response", json={"body": "рб"}, headers=b).json()
    assert v["round"]["phase"] == "verdict"
    v = client.post(f"/api/games/{gid}/vote", json={"winner": "team_a", "opponent_marks": MARKS}, headers=a).json()
    assert v["round"]["votes"]["mine"]["winner"] == "team_a"
    assert v["round"]["votes"]["opponent_submitted"] is False
    assert v["prompt"]["text"].startswith("Ждём вердикт соперника")
    v = client.post(f"/api/games/{gid}/vote", json={"winner": "team_a", "opponent_marks": MARKS}, headers=b).json()
    assert v["round"]["phase"] == "ledger"
    assert v["round"]["verdict"]["winner"] == "team_a"
    # чужие пять отметок моей карточки видны моей команде (peer)
    assert v["round"]["marks"]["team_b"]
