"""友人への警告配信を、本人の事前確認で一段止める安全装置。

スコア低下を検出しても即座には配信せず、まず本人のLINEに確認を出す。

- 😌 配信しない → suppressed（配信せず終了）
- 📨 今すぐ配信 → released（その場で配信）
- ⏰ 24時間待つ → 期限を延ばす（最大 MAX_SNOOZES 回）
- 無応答           → 期限を過ぎたら auto_released（本当に配信する）

「無視し続けた時だけ配信される」のが肝。本人が応答できない状態そのものが
警告の理由なので、無応答は取り消しではなく GO として扱う。
CRITICAL は応答不能の可能性が高いぶん待ち時間を短くする
（notification_hold_hours_critical、既定6時間）。

期限前にスコアが戻った場合は recovered として自動で取り消す。
確認中に更に重い遷移が起きた場合は、古い確認を superseded にして出し直す。

LINE_OWNER_USER_ID 未設定、または NOTIFICATION_HOLD_ENABLED=false なら
この仕組みは丸ごと無効になり、従来どおり即時配信される。
"""
import json
import logging
from datetime import datetime, timedelta

from ..config import settings
from ..database import get_db_context
from .line_notify import reply_line_message, send_line_messages, send_line_notification
from .notification import CULTURAL_ORDER, HEALTH_ORDER

logger = logging.getLogger(__name__)

POSTBACK_PREFIX = "nh:"

# 未応答時のリマインド間隔。CRITICALは短く突く。
PROMPT_INTERVAL_HOURS = 6
PROMPT_INTERVAL_HOURS_CRITICAL = 2
# 「24時間待つ」の延長幅と上限。無制限に延長できると安全装置の意味がなくなる。
SNOOZE_HOURS = 24
MAX_SNOOZES = 2

ACTION_SUPPRESS = "ok"
ACTION_SEND = "send"
ACTION_SNOOZE = "snooze"

_STATUS_LABELS = {
    "suppressed": "配信しない",
    "released": "配信済み",
    "auto_released": "自動配信済み",
    "recovered": "回復により取り消し",
    "superseded": "新しい確認に置き換え済み",
}


def _now() -> datetime:
    """テストから差し替えられるよう関数にしている（DBと同じくUTC naive）。"""
    return datetime.utcnow()


def _iso(dt: datetime) -> str:
    return dt.isoformat(sep=" ", timespec="seconds")


def _jst(dt: datetime) -> str:
    return (dt + timedelta(hours=9)).strftime("%-m/%-d %H:%M")


def is_enabled() -> bool:
    """本人の宛先が分かっていて、機能が有効なときだけゲートを挟む。

    通知そのものがOFFなら保留も進めない（毎時tickが、通知を止めた後の
    保留を勝手に配信してしまわないように）。
    """
    return bool(
        settings.notification_enabled
        and settings.notification_hold_enabled
        and settings.line_owner_user_id
    )


# --- 遷移の読み取り ---


def _targets(transitions: list[str]) -> tuple[str | None, str | None]:
    """遷移文字列から到達先ステータス (health, cultural) を取り出す。"""
    health = cultural = None
    for t in transitions:
        kind, _, arrow = t.partition(":")
        _, _, target = arrow.partition("->")
        if kind == "health":
            health = target
        elif kind == "cultural":
            cultural = target
    return health, cultural


def _is_critical(transitions: list[str]) -> bool:
    return _targets(transitions)[0] == "CRITICAL"


def _still_triggering(
    transitions: list[str], health_status: str, cultural_status: str
) -> bool:
    """確認を出した理由が今も成立しているか（片方でも残っていれば True）。"""
    health, cultural = _targets(transitions)
    if health and HEALTH_ORDER.get(health_status, 0) >= HEALTH_ORDER[health]:
        return True
    if cultural and CULTURAL_ORDER.get(cultural_status, 0) >= CULTURAL_ORDER[cultural]:
        return True
    return False


def _hold_hours(critical: bool) -> int:
    return (
        settings.notification_hold_hours_critical
        if critical
        else settings.notification_hold_hours
    )


def _prompt_interval_hours(severity: str) -> int:
    return (
        PROMPT_INTERVAL_HOURS_CRITICAL
        if severity == "critical"
        else PROMPT_INTERVAL_HOURS
    )


# --- メッセージ ---


def _transition_label(t: str) -> str:
    kind, _, arrow = t.partition(":")
    return ("健康 " if kind == "health" else "文化 ") + arrow


def build_prompt_message(hold: dict, now: datetime) -> dict:
    """本人に出す確認メッセージ（Quick Reply付き）を組み立てる。"""
    transitions = json.loads(hold["transitions"])
    release_after = datetime.fromisoformat(hold["release_after"])
    remaining_h = max(0, round((release_after - now).total_seconds() / 3600))

    if hold["prompts_sent"]:
        head = f"⏰ 配信確認（残り約{remaining_h}時間）"
    else:
        head = "🔔 [health.ojimpo.com] 配信確認"

    lines = [
        head,
        f"健康: {hold['health_status']} ({hold['health_score']:.0f})"
        f" / 文化: {hold['cultural_status']} ({hold['cultural_score']:.0f})",
        "検出: " + " / ".join(_transition_label(t) for t in transitions),
        f"このまま応答がないと {_jst(release_after)} JST に友人へ通知が配信されます。",
        "大丈夫なら「配信しない」を押してください。",
    ]

    items = [
        ("😌 配信しない", ACTION_SUPPRESS),
        ("📨 今すぐ配信", ACTION_SEND),
    ]
    if hold["snoozes"] < MAX_SNOOZES:
        items.append(("⏰ 24時間待つ", ACTION_SNOOZE))

    return {
        "type": "text",
        "text": "\n".join(lines),
        "quickReply": {
            "items": [
                {
                    "type": "action",
                    "action": {
                        "type": "postback",
                        "label": label,
                        "data": f"{POSTBACK_PREFIX}{action}:{hold['id']}",
                        "displayText": label,
                    },
                }
                for label, action in items
            ]
        },
    }


# --- DBアクセス ---


async def _fetch_pending() -> dict | None:
    async with get_db_context() as db:
        rows = await db.execute_fetchall(
            "SELECT * FROM notification_holds WHERE status = 'pending' ORDER BY id DESC LIMIT 1"
        )
    return dict(rows[0]) if rows else None


async def _fetch(hold_id: int) -> dict | None:
    async with get_db_context() as db:
        rows = await db.execute_fetchall(
            "SELECT * FROM notification_holds WHERE id = ?", (hold_id,)
        )
    return dict(rows[0]) if rows else None


async def _resolve(hold_id: int, status: str) -> None:
    async with get_db_context() as db:
        await db.execute(
            "UPDATE notification_holds SET status = ?, resolved_at = ? WHERE id = ?",
            (status, _iso(_now()), hold_id),
        )
        await db.commit()


async def _mark_prompted(hold_id: int, now: datetime) -> None:
    async with get_db_context() as db:
        await db.execute(
            """UPDATE notification_holds
            SET prompts_sent = prompts_sent + 1, last_prompt_at = ?
            WHERE id = ?""",
            (_iso(now), hold_id),
        )
        await db.commit()


# --- 本体 ---


async def open_hold(
    transitions: list[str],
    health_status: str,
    health_score: float,
    cultural_status: str,
    cultural_score: float,
) -> bool:
    """配信を保留して本人に確認を送る。保留したら True（呼び出し側は配信しない）。

    無効設定なら False を返し、呼び出し側がそのまま即時配信する。
    """
    if not is_enabled():
        return False

    now = _now()
    critical = _is_critical(transitions)
    release_after = now + timedelta(hours=_hold_hours(critical))

    async with get_db_context() as db:
        # 確認中に更に悪化した場合は、古い確認を畳んで新しい内容で出し直す
        await db.execute(
            "UPDATE notification_holds SET status = 'superseded', resolved_at = ? WHERE status = 'pending'",
            (_iso(now),),
        )
        cursor = await db.execute(
            """INSERT INTO notification_holds
            (created_at, transitions, severity, health_status, cultural_status,
             health_score, cultural_score, release_after)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                _iso(now),
                json.dumps(transitions),
                "critical" if critical else "normal",
                health_status,
                cultural_status,
                health_score,
                cultural_score,
                _iso(release_after),
            ),
        )
        hold_id = cursor.lastrowid
        await db.commit()

    logger.info(
        "Notification hold opened: id=%d transitions=%s release_after=%s",
        hold_id, transitions, _iso(release_after),
    )
    await _send_prompt(await _fetch(hold_id), now)
    return True


async def _send_prompt(hold: dict, now: datetime) -> None:
    """確認/リマインドを本人にpushする。

    push失敗時はカウンタを進めない（次のtickで再送される）。LINEが死んでいる間に
    確認だけ消費してしまうと、本人が見ないまま自動配信されるため。
    """
    try:
        await send_line_messages(
            settings.line_owner_user_id, [build_prompt_message(hold, now)]
        )
    except Exception:
        logger.exception("Notification hold: prompt push failed (id=%s)", hold["id"])
        return
    await _mark_prompted(hold["id"], now)


async def tick(scores: dict | None = None) -> None:
    """確認中の保留を1件進める（ingest後と、毎時のスケジューラから呼ばれる）。

    リマインド間隔・期限で判断するので、多少余分に呼ばれても二重送信はしない。
    """
    if not is_enabled():
        return
    hold = await _fetch_pending()
    if hold is None:
        return

    if scores is None:
        from .scoring import calculate_scores

        scores = await calculate_scores()
    health_status, cultural_status, health_score, cultural_score = _unpack(scores)

    now = _now()
    transitions = json.loads(hold["transitions"])

    if not _still_triggering(transitions, health_status, cultural_status):
        await _resolve(hold["id"], "recovered")
        logger.info("Notification hold recovered before release: id=%d", hold["id"])
        await _notify_owner(
            "✅ スコアが戻ったので、友人への通知はキャンセルしました\n"
            f"健康: {health_status} ({health_score:.0f}) / 文化: {cultural_status} ({cultural_score:.0f})"
        )
        return

    if now >= datetime.fromisoformat(hold["release_after"]):
        await release(hold, "auto_released", scores)
        return

    last = hold["last_prompt_at"]
    interval = timedelta(hours=_prompt_interval_hours(hold["severity"]))
    if last is None or now - datetime.fromisoformat(last) >= interval:
        await _send_prompt(hold, now)


async def release(hold: dict, resolution: str, scores: dict | None = None) -> None:
    """保留を解除して実際に友人へ配信する。

    配信内容は保留時ではなく解除時点のスコアで作る（保留中に更に悪化しうるため）。
    """
    from .notification import send_notifications

    if scores is None:
        from .scoring import calculate_scores

        scores = await calculate_scores()
    health_status, cultural_status, health_score, cultural_score = _unpack(scores)

    await _resolve(hold["id"], resolution)
    logger.info("Notification hold released: id=%d (%s)", hold["id"], resolution)

    await send_notifications(
        json.loads(hold["transitions"]),
        health_status,
        health_score,
        cultural_status,
        cultural_score,
    )

    if resolution == "auto_released":
        await _notify_owner(
            "📨 応答がなかったので、友人への通知を配信しました\n"
            f"健康: {health_status} ({health_score:.0f}) / 文化: {cultural_status} ({cultural_score:.0f})"
        )


def _unpack(scores: dict) -> tuple[str, str, float, float]:
    health = scores["health_status"]
    cultural = scores["cultural_status"]
    return (
        getattr(health, "value", health),
        getattr(cultural, "value", cultural),
        scores["baseline_avg"],
        scores["cultural_pct"],
    )


async def _notify_owner(text: str) -> None:
    try:
        await send_line_notification(settings.line_owner_user_id, text)
    except Exception:
        logger.exception("Notification hold: owner push failed")


# --- LINE postback ---


async def handle_postback_event(event: dict) -> None:
    """`nh:<action>:<id>` のpostbackを処理する（本人以外は無視）。"""
    user_id = (event.get("source") or {}).get("userId", "")
    if not user_id or user_id != settings.line_owner_user_id:
        logger.info("Notification hold: postback from non-owner ignored")
        return

    data = (event.get("postback") or {}).get("data", "")
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != "nh" or not parts[2].isdigit():
        logger.info("Notification hold: unknown postback data ignored: %s", data[:50])
        return
    action, hold_id = parts[1], int(parts[2])

    reply_token = event.get("replyToken")
    hold = await _fetch(hold_id)
    if hold is None:
        await _reply(reply_token, "その確認は見つかりませんでした")
        return
    if hold["status"] != "pending":
        label = _STATUS_LABELS.get(hold["status"], hold["status"])
        await _reply(reply_token, f"この確認は処理済みです（{label}）")
        return

    if action == ACTION_SUPPRESS:
        await _resolve(hold_id, "suppressed")
        logger.info("Notification hold suppressed by owner: id=%d", hold_id)
        await _reply(reply_token, "😌 友人への通知は送りません。記録しました")

    elif action == ACTION_SEND:
        # replyTokenは1分で切れるので先に返す。release()が配信前にstatusを進めるので
        # tickや連打と二重配信にはならない
        await _reply(reply_token, "📨 いま友人に配信します")
        try:
            await release(hold, "released")
        except Exception:
            logger.exception("Notification hold: manual release failed (id=%d)", hold_id)
            await _notify_owner("⚠ 配信中にエラーが発生しました。ログを確認してください")

    elif action == ACTION_SNOOZE:
        if hold["snoozes"] >= MAX_SNOOZES:
            await _reply(
                reply_token,
                "これ以上は延長できません。大丈夫なら「配信しない」を押してください",
            )
            return
        now = _now()
        new_deadline = now + timedelta(hours=SNOOZE_HOURS)
        async with get_db_context() as db:
            await db.execute(
                """UPDATE notification_holds
                SET snoozes = snoozes + 1, release_after = ?, last_prompt_at = ?
                WHERE id = ?""",
                (_iso(new_deadline), _iso(now), hold_id),
            )
            await db.commit()
        left = MAX_SNOOZES - hold["snoozes"] - 1
        suffix = f"（あと{left}回延長できます）" if left else "（延長はこれが最後です）"
        await _reply(
            reply_token, f"⏰ {_jst(new_deadline)} JST まで待ちます{suffix}"
        )

    else:
        logger.info("Notification hold: unknown action ignored: %s", action[:20])


async def _reply(reply_token: str | None, text: str) -> None:
    if not reply_token:
        return
    try:
        await reply_line_message(reply_token, text)
    except Exception:
        logger.exception("Notification hold: reply failed")
