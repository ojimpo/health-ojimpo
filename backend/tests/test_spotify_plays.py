"""Spotify recently-played 影データと Last.fm 乖離検知のテスト。

この仕組みの存在理由は、Last.fm の停止（scrobbler 側の障害）を
翌日に検知すること。守るべき性質:
- 乖離しても自動では除外しない（本人に聞くだけ）
- 「本当に聴いていない日」（Spotify 再生も少ない）では発火しない
- 聞き直しは 14 日抑制（measurement_state.asked_at を共用）
- postback は measurement_ask の既存 handler で処理できる形式
"""
from datetime import datetime, timezone

import pytest

from app.config import settings
from app.database import get_db_context
from app.services import measurement_ask as ask
from app.services import measurement_state as ms
from app.services import spotify_plays as sp

NOW = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)
OWNER = "U_owner"


@pytest.fixture
def owner(monkeypatch):
    monkeypatch.setattr(settings, "line_owner_user_id", OWNER)
    return OWNER


@pytest.fixture
def sent(monkeypatch):
    box = []

    async def fake_send(user_id, messages):
        box.append((user_id, messages))

    monkeypatch.setattr(sp, "send_line_messages", fake_send)
    return box


def _item(played_at, track_id="t1", name="Track", artist="Artist"):
    return {
        "played_at": played_at,
        "track": {
            "id": track_id,
            "name": name,
            "duration_ms": 200000,
            "artists": [{"name": artist}],
        },
    }


async def _add_plays(day: str, count: int):
    items = [
        _item(f"{day}T10:{i:02d}:00.000Z", track_id=f"t_{day}_{i}") for i in range(count)
    ]
    await sp.store_plays(items)


async def _add_scrobbles(day: str, count: int):
    async with get_db_context() as db:
        for i in range(count):
            await db.execute(
                """INSERT INTO lastfm_scrobbles
                (track_name, artist_name, scrobbled_at, scrobbled_date, duration_seconds)
                VALUES (?, 'a', ?, ?, 240)""",
                (f"s_{day}_{i}", 1700000000 + i, day),
            )
        await db.commit()


# --- 取り込み ---


async def test_store_plays_dedup_and_utc_date(test_db):
    items = [_item("2026-08-16T23:30:00.000Z"), _item("2026-08-16T23:30:00.000Z")]
    assert await sp.store_plays(items) == 1
    # 同じ再生を再取得しても増えない（recently-played は毎時重複して返る）
    assert await sp.store_plays(items) == 0
    async with get_db_context() as db:
        rows = await db.execute_fetchall(
            "SELECT play_date FROM spotify_play_history"
        )
    # UTC 日付で保存（JST に寄せない。lastfm の scrobbled_date と同じ基準）
    assert [r[0] for r in rows] == ["2026-08-16"]


# --- 乖離判定 ---


async def test_divergence_asks_owner(test_db, owner, sent):
    await _add_plays("2026-08-15", 30)
    await _add_plays("2026-08-16", 30)
    await _add_scrobbles("2026-08-15", 2)
    await _add_scrobbles("2026-08-16", 0)

    assert await sp.check_lastfm_divergence(now=NOW) is True
    assert sent[0][0] == OWNER
    text = sent[0][1][0]["text"]
    assert "Spotify 30曲" in text
    assert len(sent[0][1][0]["quickReply"]["items"]) == 2
    # 聞いただけでは除外しない
    assert await ms.get_broken_sources() == {}
    # asked_at が記録され、聞き直しが抑制される
    assert await sp.check_lastfm_divergence(now=NOW) is False


async def test_no_ask_when_lastfm_healthy(test_db, owner, sent):
    await _add_plays("2026-08-15", 30)
    await _add_plays("2026-08-16", 30)
    await _add_scrobbles("2026-08-15", 28)
    await _add_scrobbles("2026-08-16", 25)
    assert await sp.check_lastfm_divergence(now=NOW) is False
    assert sent == []


async def test_no_ask_when_not_listening(test_db, owner, sent):
    """Spotify 再生自体が少ない日は「聴いていないだけ」と区別できないので発火しない。"""
    await _add_plays("2026-08-15", 5)
    await _add_plays("2026-08-16", 5)
    assert await sp.check_lastfm_divergence(now=NOW) is False
    assert sent == []


async def test_no_ask_on_single_day_divergence(test_db, owner, sent):
    """1日だけの乖離は日付境界のズレがありうるので聞かない。"""
    await _add_plays("2026-08-15", 30)
    await _add_scrobbles("2026-08-15", 28)
    await _add_plays("2026-08-16", 30)
    await _add_scrobbles("2026-08-16", 0)
    assert await sp.check_lastfm_divergence(now=NOW) is False
    assert sent == []


async def test_no_ask_when_already_broken(test_db, owner, sent):
    await ms.mark_broken("lastfm", ms.REASON_USER_REPORTED, "test")
    await _add_plays("2026-08-15", 30)
    await _add_plays("2026-08-16", 30)
    assert await sp.check_lastfm_divergence(now=NOW) is False
    assert sent == []


async def test_no_ask_without_owner(test_db, sent, monkeypatch):
    monkeypatch.setattr(settings, "line_owner_user_id", "")
    await _add_plays("2026-08-15", 30)
    await _add_plays("2026-08-16", 30)
    assert await sp.check_lastfm_divergence(now=NOW) is False
    assert sent == []


# --- postback 互換性 ---


async def test_postback_flows_through_measurement_ask(test_db, owner, sent, monkeypatch):
    """質問の postback が既存の `ms:` handler で処理でき、broken まで到達する。"""
    replies = []

    async def fake_reply(token, message):
        replies.append(message)

    monkeypatch.setattr(ask, "reply_line_message", fake_reply)

    await _add_plays("2026-08-15", 30)
    await _add_plays("2026-08-16", 30)
    assert await sp.check_lastfm_divergence(now=NOW) is True

    data = sent[0][1][0]["quickReply"]["items"][0]["action"]["data"]
    assert data == "ms:broken:lastfm"
    await ask.handle_postback_event(
        {
            "source": {"userId": OWNER},
            "replyToken": "rt",
            "postback": {"data": data},
        }
    )
    broken = await ms.get_broken_sources()
    assert "lastfm" in broken
    assert broken["lastfm"]["reason"] == ms.REASON_USER_REPORTED
