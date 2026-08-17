"""取得量急減の判断を本人に聞く経路のテスト。

この仕組みの存在理由は、急減が「本物の活動低下」と「計測断」のどちらでも
同じ形になり、データからは原理的に区別できないこと。したがって
- 聞いただけでは何も変えない（答えを待つ）
- 「やってないだけ」なら低いまま軸に残す
- 「壊れてそう」なら初めて軸から外す
が守られていることを見る。
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.config import settings
from app.services import measurement_ask as ask
from app.services import measurement_state as ms

from .conftest import add_source

NOW = datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc)
OWNER = "U_owner"


@pytest.fixture
def owner(monkeypatch):
    monkeypatch.setattr(settings, "line_owner_user_id", OWNER)
    return OWNER


@pytest.fixture
def sent(monkeypatch):
    """送信したLINEメッセージを集める。"""
    box = []
    async def fake_send(user_id, messages):
        box.append((user_id, messages))
    async def fake_reply(token, message):
        box.append(("reply", message))
    monkeypatch.setattr(ask, "send_line_messages", fake_send)
    monkeypatch.setattr(ask, "reply_line_message", fake_reply)
    return box


def _report(source_id="lastfm", name="音楽 (Last.fm)", collapse=True):
    return [{
        "id": source_id,
        "name": name,
        "level": "warn" if collapse else "ok",
        "detail": "取得量が急減（直近14日 46 / 平常時 4,347 = 1%）",
        "volume_collapse": collapse,
        "reason": None,
    }]


def _postback(action, source_id, user_id=OWNER):
    return {
        "type": "postback",
        "source": {"userId": user_id},
        "replyToken": "rt",
        "postback": {"data": f"{ask.POSTBACK_PREFIX}{action}:{source_id}"},
    }


# --- 質問の送信 ---


async def test_asks_on_collapse(test_db, owner, sent):
    await add_source("lastfm", "music")
    assert await ask.ask_about_collapses(_report(), now=NOW) == ["lastfm"]
    assert sent[0][0] == OWNER
    assert "急減" in sent[0][1][0]["text"]
    assert len(sent[0][1][0]["quickReply"]["items"]) == 2


async def test_asking_does_not_change_the_score(test_db, owner, sent):
    """答えが来るまでは軸から外さない。判断がつかないうちに外す方が危険。"""
    await add_source("lastfm", "music")
    await ask.ask_about_collapses(_report(), now=NOW)
    assert await ms.get_broken_sources() == {}


async def test_no_ask_without_collapse(test_db, owner, sent):
    await add_source("lastfm", "music")
    assert await ask.ask_about_collapses(_report(collapse=False), now=NOW) == []
    assert sent == []


async def test_no_ask_when_already_known_broken(test_db, owner, sent):
    """答えが出ているソースは聞き直さない。"""
    await add_source("lastfm", "music")
    await ms.mark_broken("lastfm", ms.REASON_USER_REPORTED)
    assert await ask.ask_about_collapses(_report(), now=NOW) == []


async def test_not_asked_again_within_interval(test_db, owner, sent):
    await add_source("lastfm", "music")
    await ask.ask_about_collapses(_report(), now=NOW)
    assert await ask.ask_about_collapses(_report(), now=NOW + timedelta(days=7)) == []
    # record_asked は実時刻(datetime('now'))で記録するので、固定NOWからの相対だと
    # 実行時刻によって14日に届かないことがある。実時刻基準で間隔を超えさせる。
    later = datetime.now(timezone.utc) + timedelta(days=ask.ASK_INTERVAL_DAYS + 1)
    assert await ask.ask_about_collapses(_report(), now=later) == ["lastfm"]


async def test_skipped_without_owner(test_db, monkeypatch, sent):
    monkeypatch.setattr(settings, "line_owner_user_id", "")
    assert await ask.ask_about_collapses(_report(), now=NOW) == []


# --- 回答の処理 ---


async def test_answer_broken_excludes(test_db, owner, sent):
    await add_source("lastfm", "music")
    await ask.handle_postback_event(_postback(ask.ACTION_BROKEN, "lastfm"))
    broken = await ms.get_broken_sources()
    assert broken["lastfm"]["reason"] == ms.REASON_USER_REPORTED


async def test_answer_real_keeps_it_in_the_axis(test_db, owner, sent):
    """「やってないだけ」は観測として正しいので、低いまま軸に残す。"""
    await add_source("lastfm", "music")
    await ask.handle_postback_event(_postback(ask.ACTION_REAL, "lastfm"))
    assert await ms.get_broken_sources() == {}


async def test_answer_real_undoes_previous_broken(test_db, owner, sent):
    await add_source("lastfm", "music")
    await ms.mark_broken("lastfm", ms.REASON_USER_REPORTED)
    await ask.handle_postback_event(_postback(ask.ACTION_REAL, "lastfm"))
    assert await ms.get_broken_sources() == {}


async def test_non_owner_postback_ignored(test_db, owner, sent):
    """友人が誤操作してもスコアを動かせない。"""
    await add_source("lastfm", "music")
    await ask.handle_postback_event(_postback(ask.ACTION_BROKEN, "lastfm", user_id="U_other"))
    assert await ms.get_broken_sources() == {}


async def test_malformed_postback_ignored(test_db, owner, sent):
    await add_source("lastfm", "music")
    for data in ("ms:", "ms:broken", "nh:broken:lastfm", "ms:unknown:lastfm"):
        event = {
            "type": "postback",
            "source": {"userId": OWNER},
            "replyToken": "rt",
            "postback": {"data": data},
        }
        await ask.handle_postback_event(event)
    assert await ms.get_broken_sources() == {}
