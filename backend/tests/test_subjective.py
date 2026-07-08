"""Tests for subjective feedback: LINE webhook + answer recording + Oura steps aggregate."""
import base64
import hashlib
import hmac
import json

import httpx
import pytest
from fastapi import FastAPI

from app import database
from app.config import settings
from app.routers import notification
from app.services.subjective import record_answer
from app.sources.oura_steps import OuraStepsAdapter

from .conftest import add_record, add_source

OWNER = "U" + "a" * 32
SECRET = "test-channel-secret"


def _sign(body: bytes) -> str:
    digest = hmac.new(SECRET.encode(), body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


WEBHOOK_PATH = "/api/notification/line/webhook"


def _client() -> httpx.AsyncClient:
    app = FastAPI()
    app.include_router(notification.router, prefix="/api")
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def _postback_body(user_id: str, data: str) -> bytes:
    return json.dumps({
        "events": [{
            "type": "postback",
            "source": {"userId": user_id},
            "postback": {"data": data},
        }]
    }).encode()


@pytest.fixture(autouse=True)
def line_settings(monkeypatch):
    monkeypatch.setattr(settings, "line_channel_secret", SECRET)
    monkeypatch.setattr(settings, "line_owner_user_id", OWNER)


async def _fetch_feedback():
    async with database.get_db_context() as db:
        return await db.execute_fetchall(
            "SELECT date, answer, health_status FROM subjective_feedback"
        )


async def test_record_answer_stores_snapshot(test_db):
    await add_source("lastfm", "music", base_value=700)
    await add_record("2026-07-01", "lastfm", "music", 100)
    await record_answer("2026-07-02", "good")

    rows = await _fetch_feedback()
    assert len(rows) == 1
    assert rows[0][0] == "2026-07-02"
    assert rows[0][1] == "good"
    assert rows[0][2] in ("NORMAL", "CAUTION", "CRITICAL")


async def test_record_answer_overwrite_same_day(test_db):
    await record_answer("2026-07-02", "good")
    await record_answer("2026-07-02", "bad")
    rows = await _fetch_feedback()
    assert len(rows) == 1
    assert rows[0][1] == "bad"


async def test_webhook_rejects_invalid_signature(test_db):
    body = _postback_body(OWNER, "sf:good:2026-07-02")
    async with _client() as client:
        resp = await client.post(
            WEBHOOK_PATH, content=body,
            headers={"X-Line-Signature": "invalid"},
        )
    assert resp.status_code == 403
    assert await _fetch_feedback() == []


async def test_webhook_records_owner_postback(test_db):
    body = _postback_body(OWNER, "sf:normal:2026-07-02")
    async with _client() as client:
        resp = await client.post(
            WEBHOOK_PATH, content=body,
            headers={"X-Line-Signature": _sign(body)},
        )
    assert resp.status_code == 200
    rows = await _fetch_feedback()
    assert len(rows) == 1
    assert rows[0][1] == "normal"


async def test_webhook_ignores_non_owner(test_db):
    body = _postback_body("U" + "b" * 32, "sf:good:2026-07-02")
    async with _client() as client:
        resp = await client.post(
            WEBHOOK_PATH, content=body,
            headers={"X-Line-Signature": _sign(body)},
        )
    assert resp.status_code == 200
    assert await _fetch_feedback() == []


async def test_webhook_ignores_unknown_postback_data(test_db):
    for data in ("sf:great:2026-07-02", "other:good:2026-07-02", "sf:good"):
        body = _postback_body(OWNER, data)
        async with _client() as client:
            resp = await client.post(
                WEBHOOK_PATH, content=body,
                headers={"X-Line-Signature": _sign(body)},
            )
        assert resp.status_code == 200
    assert await _fetch_feedback() == []


async def test_oura_steps_aggregate(test_db):
    async with database.get_db_context() as db:
        await db.execute(
            "INSERT INTO oura_activity_daily (date, steps, activity_score) VALUES (?, ?, ?)",
            ("2026-07-01", 8234, 90),
        )
        await db.execute(
            "INSERT INTO oura_activity_daily (date, steps) VALUES (?, NULL)",
            ("2026-07-02",),
        )
        await db.commit()

    await OuraStepsAdapter().aggregate()

    async with database.get_db_context() as db:
        rows = await db.execute_fetchall(
            "SELECT date, source, category, raw_value, raw_unit FROM activity_records"
        )
    assert [tuple(r) for r in rows] == [
        ("2026-07-01", "oura_steps", "exercise", 8234.0, "steps")
    ]
