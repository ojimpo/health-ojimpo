"""配信前の本人確認ゲート（services/notification_hold.py）のテスト。

「本人が無視し続けた時だけ友人に配信される」という安全装置の挙動を、
LINE送信とスコア計算をスタブして時計を固定した状態で確認する。
"""
import json
from datetime import datetime, timedelta

import pytest

from app import database
from app.config import settings
from app.models.enums import CulturalStatus, HealthStatus
from app.services import notification, notification_hold

OWNER = "U" + "b" * 32
T0 = datetime(2026, 8, 16, 0, 0, 0)


def _scores(health="CAUTION", cultural="RICH", h=62.0, c=118.0):
    return {
        "health_status": HealthStatus(health),
        "cultural_status": CulturalStatus(cultural),
        "baseline_avg": h,
        "cultural_pct": c,
    }


@pytest.fixture
def line(monkeypatch):
    """LINE送信をすべて捕捉する。pushes/replies/broadcasts を検査する。"""
    captured = {"pushes": [], "replies": [], "broadcasts": []}

    async def fake_send_messages(user_id, messages):
        captured["pushes"].append((user_id, messages))

    async def fake_send_text(user_id, text):
        captured["pushes"].append((user_id, [{"type": "text", "text": text}]))

    async def fake_reply(token, text):
        captured["replies"].append(text)

    async def fake_broadcast(transitions, hs, h, cs, c):
        captured["broadcasts"].append((transitions, hs, h, cs, c))

    monkeypatch.setattr(settings, "line_owner_user_id", OWNER)
    monkeypatch.setattr(settings, "notification_enabled", True)
    monkeypatch.setattr(settings, "notification_hold_enabled", True)
    monkeypatch.setattr(notification_hold, "send_line_messages", fake_send_messages)
    monkeypatch.setattr(notification_hold, "send_line_notification", fake_send_text)
    monkeypatch.setattr(notification_hold, "reply_line_message", fake_reply)
    monkeypatch.setattr(notification, "send_notifications", fake_broadcast)
    return captured


@pytest.fixture
def clock(monkeypatch):
    """`now` を書き換えると notification_hold から見える時刻が変わる。"""

    class Clock:
        now = T0

        def advance(self, hours):
            Clock.now = Clock.now + timedelta(hours=hours)

    monkeypatch.setattr(notification_hold, "_now", lambda: Clock.now)
    return Clock()


async def _holds():
    async with database.get_db_context() as db:
        rows = await db.execute_fetchall(
            "SELECT * FROM notification_holds ORDER BY id"
        )
    return [dict(r) for r in rows]


def _postback(action, hold_id, user_id=OWNER):
    return {
        "type": "postback",
        "source": {"userId": user_id},
        "postback": {"data": f"nh:{action}:{hold_id}"},
        "replyToken": "rt",
    }


# --- 保留の作成 ---


async def test_open_hold_defers_broadcast_and_prompts_owner(test_db, line, clock):
    held = await notification_hold.open_hold(
        ["health:NORMAL->CAUTION"], "CAUTION", 62.0, "RICH", 118.0
    )
    assert held is True
    assert line["broadcasts"] == []

    rows = await _holds()
    assert len(rows) == 1
    assert rows[0]["status"] == "pending"
    assert rows[0]["severity"] == "normal"
    assert rows[0]["prompts_sent"] == 1
    # 既定24時間後が期限
    assert rows[0]["release_after"] == (T0 + timedelta(hours=24)).isoformat(sep=" ")

    user_id, messages = line["pushes"][0]
    assert user_id == OWNER
    labels = [
        i["action"]["data"] for i in messages[0]["quickReply"]["items"]
    ]
    assert labels == ["nh:ok:1", "nh:send:1", "nh:snooze:1"]
    assert "配信されます" in messages[0]["text"]


async def test_critical_gets_shorter_deadline(test_db, line, clock):
    await notification_hold.open_hold(
        ["health:CAUTION->CRITICAL"], "CRITICAL", 22.0, "LOW", 30.0
    )
    rows = await _holds()
    assert rows[0]["severity"] == "critical"
    assert rows[0]["release_after"] == (T0 + timedelta(hours=6)).isoformat(sep=" ")


@pytest.mark.parametrize(
    "attr,value",
    [
        ("line_owner_user_id", ""),
        ("notification_hold_enabled", False),
        ("notification_enabled", False),
    ],
)
async def test_disabled_sends_immediately(test_db, line, clock, monkeypatch, attr, value):
    monkeypatch.setattr(settings, attr, value)
    held = await notification_hold.open_hold(
        ["health:NORMAL->CAUTION"], "CAUTION", 62.0, "RICH", 118.0
    )
    assert held is False
    assert await _holds() == []


async def test_disabling_notifications_freezes_pending_hold(test_db, line, clock, monkeypatch):
    """保留中に通知をOFFにしたら、期限が来ても勝手に配信しない。"""
    await notification_hold.open_hold(
        ["health:NORMAL->CAUTION"], "CAUTION", 62.0, "RICH", 118.0
    )
    monkeypatch.setattr(settings, "notification_enabled", False)
    clock.advance(48)
    await notification_hold.tick(_scores())
    assert line["broadcasts"] == []
    assert (await _holds())[0]["status"] == "pending"


async def test_second_transition_supersedes_pending_hold(test_db, line, clock):
    await notification_hold.open_hold(
        ["health:NORMAL->CAUTION"], "CAUTION", 62.0, "RICH", 118.0
    )
    clock.advance(1)
    await notification_hold.open_hold(
        ["health:CAUTION->CRITICAL"], "CRITICAL", 30.0, "RICH", 118.0
    )
    rows = await _holds()
    assert [r["status"] for r in rows] == ["superseded", "pending"]
    assert line["broadcasts"] == []


async def test_prompt_push_failure_keeps_counter_for_retry(test_db, line, clock, monkeypatch):
    async def boom(user_id, messages):
        raise RuntimeError("LINE down")

    monkeypatch.setattr(notification_hold, "send_line_messages", boom)
    assert await notification_hold.open_hold(
        ["health:NORMAL->CAUTION"], "CAUTION", 62.0, "RICH", 118.0
    ) is True
    rows = await _holds()
    assert rows[0]["prompts_sent"] == 0
    assert rows[0]["last_prompt_at"] is None
    assert rows[0]["status"] == "pending"


# --- 無応答での自動配信 ---


async def test_reminder_then_auto_release_when_ignored(test_db, line, clock):
    await notification_hold.open_hold(
        ["health:NORMAL->CAUTION"], "CAUTION", 62.0, "RICH", 118.0
    )
    assert len(line["pushes"]) == 1

    # リマインド間隔前のtickは何もしない
    clock.advance(1)
    await notification_hold.tick(_scores())
    assert len(line["pushes"]) == 1

    # 6時間後にリマインド
    clock.advance(5)
    await notification_hold.tick(_scores())
    assert len(line["pushes"]) == 2
    assert "残り約18時間" in line["pushes"][1][1][0]["text"]
    assert line["broadcasts"] == []

    # 期限を過ぎたら実際に配信する
    clock.advance(19)
    await notification_hold.tick(_scores())
    assert len(line["broadcasts"]) == 1
    transitions, hs, h, cs, c = line["broadcasts"][0]
    assert transitions == ["health:NORMAL->CAUTION"]
    assert (hs, cs) == ("CAUTION", "RICH")
    rows = await _holds()
    assert rows[0]["status"] == "auto_released"
    # 配信したことは本人にも伝える
    assert "配信しました" in line["pushes"][-1][1][0]["text"]


async def test_auto_release_uses_current_scores(test_db, line, clock):
    await notification_hold.open_hold(
        ["health:NORMAL->CAUTION"], "CAUTION", 62.0, "RICH", 118.0
    )
    clock.advance(25)
    await notification_hold.tick(_scores(health="CRITICAL", h=28.0))
    _, hs, h, _, _ = line["broadcasts"][0]
    assert (hs, h) == ("CRITICAL", 28.0)


async def test_released_hold_is_not_sent_twice(test_db, line, clock):
    await notification_hold.open_hold(
        ["health:NORMAL->CAUTION"], "CAUTION", 62.0, "RICH", 118.0
    )
    clock.advance(25)
    await notification_hold.tick(_scores())
    await notification_hold.tick(_scores())
    assert len(line["broadcasts"]) == 1


async def test_recovery_before_deadline_cancels(test_db, line, clock):
    await notification_hold.open_hold(
        ["health:NORMAL->CAUTION"], "CAUTION", 62.0, "RICH", 118.0
    )
    clock.advance(10)
    await notification_hold.tick(_scores(health="NORMAL", h=88.0))

    assert line["broadcasts"] == []
    rows = await _holds()
    assert rows[0]["status"] == "recovered"
    assert "キャンセル" in line["pushes"][-1][1][0]["text"]


async def test_cultural_hold_survives_health_recovery(test_db, line, clock):
    """文化LOWで出した確認は、健康が戻っただけでは取り消さない。"""
    await notification_hold.open_hold(
        ["cultural:MODERATE->LOW"], "NORMAL", 88.0, "LOW", 32.0
    )
    clock.advance(25)
    await notification_hold.tick(_scores(health="NORMAL", cultural="LOW", h=88.0, c=32.0))
    assert len(line["broadcasts"]) == 1


# --- 本人の応答 ---


async def test_owner_suppress_stops_broadcast(test_db, line, clock):
    await notification_hold.open_hold(
        ["health:NORMAL->CAUTION"], "CAUTION", 62.0, "RICH", 118.0
    )
    await notification_hold.handle_postback_event(_postback("ok", 1))

    rows = await _holds()
    assert rows[0]["status"] == "suppressed"
    assert "送りません" in line["replies"][0]

    # 期限を過ぎてももう配信されない
    clock.advance(48)
    await notification_hold.tick(_scores())
    assert line["broadcasts"] == []


async def test_owner_send_now_broadcasts(test_db, line, clock):
    await notification_hold.open_hold(
        ["health:NORMAL->CAUTION"], "CAUTION", 62.0, "RICH", 118.0
    )
    await notification_hold.handle_postback_event(_postback("send", 1))

    assert len(line["broadcasts"]) == 1
    rows = await _holds()
    assert rows[0]["status"] == "released"


async def test_snooze_extends_deadline_up_to_limit(test_db, line, clock):
    await notification_hold.open_hold(
        ["health:NORMAL->CAUTION"], "CAUTION", 62.0, "RICH", 118.0
    )
    clock.advance(20)
    await notification_hold.handle_postback_event(_postback("snooze", 1))
    rows = await _holds()
    assert rows[0]["snoozes"] == 1
    assert rows[0]["release_after"] == (T0 + timedelta(hours=44)).isoformat(sep=" ")

    # 期限が延びているので配信されない
    clock.advance(10)
    await notification_hold.tick(_scores())
    assert line["broadcasts"] == []

    await notification_hold.handle_postback_event(_postback("snooze", 1))
    await notification_hold.handle_postback_event(_postback("snooze", 1))
    rows = await _holds()
    assert rows[0]["snoozes"] == 2
    assert "これ以上は延長できません" in line["replies"][-1]

    # 上限に達したら延長ボタン自体を出さない
    msg = notification_hold.build_prompt_message(rows[0], clock.now)
    assert [i["action"]["data"] for i in msg["quickReply"]["items"]] == [
        "nh:ok:1", "nh:send:1"
    ]


async def test_postback_from_non_owner_ignored(test_db, line, clock):
    await notification_hold.open_hold(
        ["health:NORMAL->CAUTION"], "CAUTION", 62.0, "RICH", 118.0
    )
    await notification_hold.handle_postback_event(_postback("ok", 1, user_id="Uintruder"))
    rows = await _holds()
    assert rows[0]["status"] == "pending"
    assert line["replies"] == []


async def test_postback_on_resolved_hold_replies_without_effect(test_db, line, clock):
    await notification_hold.open_hold(
        ["health:NORMAL->CAUTION"], "CAUTION", 62.0, "RICH", 118.0
    )
    await notification_hold.handle_postback_event(_postback("ok", 1))
    await notification_hold.handle_postback_event(_postback("send", 1))
    assert line["broadcasts"] == []
    assert "処理済み" in line["replies"][-1]


# --- check_and_notify との結線 ---


async def test_check_and_notify_holds_instead_of_broadcasting(test_db, line, clock, monkeypatch):
    async def fake_scores(*args, **kwargs):
        return _scores()

    monkeypatch.setattr(notification, "calculate_scores", fake_scores)
    # 持続性ガードを通すため、直近3回ぶんCAUTIONを積む
    async with database.get_db_context() as db:
        for _ in range(notification.PERSISTENCE_REQUIRED):
            await db.execute(
                """INSERT INTO status_history
                (health_status, cultural_status, health_score, cultural_score)
                VALUES ('CAUTION', 'RICH', 62.0, 118.0)"""
            )
        await db.commit()

    await notification.check_and_notify()

    assert line["broadcasts"] == []
    rows = await _holds()
    assert len(rows) == 1
    assert json.loads(rows[0]["transitions"]) == ["health:NORMAL->CAUTION"]
