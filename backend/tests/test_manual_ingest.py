"""Tests for LINE-triggered manual ingest + /api/ingest/trigger auth."""
import asyncio
import base64
import hashlib
import hmac
import json

import httpx
import pytest
from fastapi import FastAPI

from app import database
from app.config import settings
from app.routers import ingest as ingest_router
from app.routers import notification
from app.services import manual_ingest

OWNER = "U" + "a" * 32
SECRET = "test-channel-secret"

WEBHOOK_PATH = "/api/notification/line/webhook"


def _sign(body: bytes) -> str:
    digest = hmac.new(SECRET.encode(), body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def _client() -> httpx.AsyncClient:
    app = FastAPI()
    app.include_router(notification.router, prefix="/api")
    app.include_router(ingest_router.router, prefix="/api")
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture(autouse=True)
def line_settings(monkeypatch):
    monkeypatch.setattr(settings, "line_channel_secret", SECRET)
    monkeypatch.setattr(settings, "line_owner_user_id", OWNER)
    manual_ingest._running = False


@pytest.fixture
def line_calls(monkeypatch):
    """Record LINE reply/push calls instead of hitting the API."""
    calls = {"reply": [], "push": []}

    async def fake_reply(token, message):
        calls["reply"].append(message)

    async def fake_push(user_id, message):
        calls["push"].append((user_id, message))

    monkeypatch.setattr(manual_ingest, "reply_line_message", fake_reply)
    monkeypatch.setattr(manual_ingest, "send_line_notification", fake_push)
    return calls


def _event(user_id=OWNER, data=manual_ingest.POSTBACK_RUN, reply_token="rt"):
    return {
        "type": "postback",
        "source": {"userId": user_id},
        "postback": {"data": data},
        "replyToken": reply_token,
    }


async def _drain_tasks():
    """Let asyncio.create_task background tasks run to completion."""
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


# --- handle_ingest_event ---


async def test_non_owner_ignored(test_db, line_calls, monkeypatch):
    ran = []

    async def fake_run():
        ran.append(True)

    monkeypatch.setattr(manual_ingest, "_run_and_report", fake_run)
    await manual_ingest.handle_ingest_event(_event(user_id="U" + "b" * 32))
    await _drain_tasks()
    assert ran == []
    assert line_calls["reply"] == []
    assert manual_ingest._running is False


async def test_unknown_postback_data_ignored(test_db, line_calls, monkeypatch):
    ran = []

    async def fake_run():
        ran.append(True)

    monkeypatch.setattr(manual_ingest, "_run_and_report", fake_run)
    await manual_ingest.handle_ingest_event(_event(data="ingest:doom"))
    await _drain_tasks()
    assert ran == []
    assert manual_ingest._running is False


async def test_owner_postback_starts_run(test_db, line_calls, monkeypatch):
    ran = []

    async def fake_run():
        ran.append(True)
        manual_ingest._running = False

    monkeypatch.setattr(manual_ingest, "_run_and_report", fake_run)
    await manual_ingest.handle_ingest_event(_event())
    assert manual_ingest._running is True
    await _drain_tasks()
    assert ran == [True]
    assert len(line_calls["reply"]) == 1
    assert "開始しました" in line_calls["reply"][0]


async def test_second_trigger_while_running_is_rejected(test_db, line_calls, monkeypatch):
    ran = []

    async def fake_run():
        ran.append(True)

    monkeypatch.setattr(manual_ingest, "_run_and_report", fake_run)
    manual_ingest._running = True
    await manual_ingest.handle_ingest_event(_event())
    await _drain_tasks()
    assert ran == []
    assert len(line_calls["reply"]) == 1
    assert "実行中" in line_calls["reply"][0]


# --- _run_and_report ---


async def test_run_and_report_pushes_summary(test_db, line_calls, monkeypatch):
    async def fake_run_all():
        async with database.get_db_context() as db:
            await db.execute(
                "INSERT INTO ingest_log (source, started_at, completed_at, status) "
                "VALUES ('lastfm', datetime('now'), datetime('now'), 'completed')"
            )
            await db.execute(
                "INSERT INTO ingest_log (source, started_at, completed_at, status) "
                "VALUES ('oura', datetime('now'), datetime('now'), 'failed')"
            )
            await db.commit()

    monkeypatch.setattr("app.services.ingest.run_all_ingest", fake_run_all)
    manual_ingest._running = True
    await manual_ingest._run_and_report()

    assert manual_ingest._running is False
    assert len(line_calls["push"]) == 1
    user_id, message = line_calls["push"][0]
    assert user_id == OWNER
    assert "1ソース成功" in message
    assert "oura" in message


async def test_run_and_report_notifies_on_crash(test_db, line_calls, monkeypatch):
    async def fake_run_all():
        raise RuntimeError("boom")

    monkeypatch.setattr("app.services.ingest.run_all_ingest", fake_run_all)
    manual_ingest._running = True
    await manual_ingest._run_and_report()

    assert manual_ingest._running is False
    assert len(line_calls["push"]) == 1
    assert "エラー" in line_calls["push"][0][1]


# --- webhook routing ---


async def test_webhook_routes_ingest_postback(test_db, monkeypatch):
    handled = []

    async def fake_handler(event):
        handled.append(event["postback"]["data"])

    monkeypatch.setattr(manual_ingest, "handle_ingest_event", fake_handler)
    body = json.dumps({"events": [_event()]}).encode()
    async with _client() as client:
        resp = await client.post(
            WEBHOOK_PATH, content=body, headers={"X-Line-Signature": _sign(body)}
        )
    assert resp.status_code == 200
    assert handled == [manual_ingest.POSTBACK_RUN]


async def test_webhook_routes_ingest_text_message(test_db, monkeypatch):
    handled = []

    async def fake_handler(event):
        handled.append(event["message"]["text"])

    monkeypatch.setattr(manual_ingest, "handle_ingest_event", fake_handler)
    body = json.dumps({
        "events": [{
            "type": "message",
            "source": {"userId": OWNER},
            "message": {"type": "text", "text": " Ingest "},
            "replyToken": "rt",
        }]
    }).encode()
    async with _client() as client:
        resp = await client.post(
            WEBHOOK_PATH, content=body, headers={"X-Line-Signature": _sign(body)}
        )
    assert resp.status_code == 200
    assert handled == [" Ingest "]


async def test_webhook_ignores_other_text_messages(test_db, monkeypatch):
    handled = []

    async def fake_handler(event):
        handled.append(event)

    monkeypatch.setattr(manual_ingest, "handle_ingest_event", fake_handler)
    body = json.dumps({
        "events": [{
            "type": "message",
            "source": {"userId": OWNER},
            "message": {"type": "text", "text": "こんにちは"},
        }]
    }).encode()
    async with _client() as client:
        resp = await client.post(
            WEBHOOK_PATH, content=body, headers={"X-Line-Signature": _sign(body)}
        )
    assert resp.status_code == 200
    assert handled == []


async def test_webhook_still_routes_subjective_postback(test_db, monkeypatch):
    sf_handled = []
    ingest_handled = []

    async def fake_sf(event):
        sf_handled.append(event)

    async def fake_ingest(event):
        ingest_handled.append(event)

    monkeypatch.setattr("app.services.subjective.handle_postback_event", fake_sf)
    monkeypatch.setattr(manual_ingest, "handle_ingest_event", fake_ingest)
    body = json.dumps({"events": [_event(data="sf:good:2026-07-19")]}).encode()
    async with _client() as client:
        resp = await client.post(
            WEBHOOK_PATH, content=body, headers={"X-Line-Signature": _sign(body)}
        )
    assert resp.status_code == 200
    assert len(sf_handled) == 1
    assert ingest_handled == []


# --- /api/ingest/trigger auth ---


@pytest.fixture
def webhook_secret(monkeypatch):
    monkeypatch.setattr(ingest_router.app_settings, "webhook_secret", "s3cret")


async def test_trigger_requires_token(test_db, webhook_secret):
    async with _client() as client:
        resp = await client.post("/api/ingest/trigger", json={"source": "all"})
    assert resp.status_code == 401


async def test_trigger_rejects_bad_token(test_db, webhook_secret):
    async with _client() as client:
        resp = await client.post(
            "/api/ingest/trigger",
            json={"source": "all"},
            headers={"Authorization": "Bearer wrong"},
        )
    assert resp.status_code == 403


async def test_trigger_all_with_token(test_db, webhook_secret, monkeypatch):
    ran = []

    async def fake_run_all():
        ran.append(True)

    monkeypatch.setattr(ingest_router, "run_all_ingest", fake_run_all)
    async with _client() as client:
        resp = await client.post(
            "/api/ingest/trigger",
            json={"source": "all"},
            headers={"Authorization": "Bearer s3cret"},
        )
    assert resp.status_code == 200
    assert resp.json() == {"status": "started", "source": "all"}
    await _drain_tasks()
    assert ran == [True]
