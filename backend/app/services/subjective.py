"""主観フィードバック: 毎晩LINEで調子を聞き、回答をスコアと共に保存する。

スコアリングモデルの「正解データ」を蓄積するための仕組み。
質問は絶対評価3択（良い/普通/悪い）。相対評価（昨日比）は微分値になり
その日のスコアと直接突き合わせられないため採用しない。
未回答の日はレコードなし（ペナルティなし）。
"""
import logging
from datetime import date

from ..config import settings
from ..database import get_db_context
from .line_notify import send_line_messages

logger = logging.getLogger(__name__)

ANSWER_LABELS = {"good": "😊 良い", "normal": "😐 普通", "bad": "😞 悪い"}


async def send_daily_question(for_date: date | None = None) -> bool:
    """本人のLINEにその日の調子を聞くQuick Reply付きメッセージを送る。

    宛先は LINE_OWNER_USER_ID のみ（notification_subscribers の友人には送らない）。
    """
    if not settings.line_owner_user_id:
        logger.info("Subjective feedback: LINE_OWNER_USER_ID not configured, skipping")
        return False
    if for_date is None:
        for_date = date.today()
    d = for_date.isoformat()

    message = {
        "type": "text",
        "text": f"今日（{for_date.month}/{for_date.day}）の調子はどうでしたか？",
        "quickReply": {
            "items": [
                {
                    "type": "action",
                    "action": {
                        "type": "postback",
                        "label": label,
                        "data": f"sf:{key}:{d}",
                        "displayText": label,
                    },
                }
                for key, label in ANSWER_LABELS.items()
            ]
        },
    }
    await send_line_messages(settings.line_owner_user_id, [message])
    logger.info("Subjective feedback: daily question sent for %s", d)
    return True


async def handle_postback_event(event: dict) -> None:
    """LINE webhookのpostbackイベントから主観フィードバック回答を記録する。

    LINE_OWNER_USER_ID 以外のuserIdは無視する（友人が誤操作しても混入しない）。
    """
    user_id = (event.get("source") or {}).get("userId", "")
    if not user_id or user_id != settings.line_owner_user_id:
        logger.info("Subjective feedback: postback from non-owner ignored")
        return

    data = (event.get("postback") or {}).get("data", "")
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != "sf" or parts[1] not in ANSWER_LABELS:
        logger.info("Subjective feedback: unknown postback data ignored: %s", data[:50])
        return
    _, answer, for_date = parts
    await record_answer(for_date, answer)

    reply_token = event.get("replyToken")
    if reply_token:
        from .line_notify import reply_line_message

        await reply_line_message(reply_token, f"{ANSWER_LABELS[answer]} で記録しました")


async def record_answer(for_date: str, answer: str) -> None:
    """回答を、その日の健康/文化スコアのスナップショットと共に保存する。

    同日の再回答は上書き（answer/answered_atのみ更新、スナップショットは初回のまま）。
    """
    from .scoring import calculate_scores

    scores = await calculate_scores(date.fromisoformat(for_date))
    async with get_db_context() as db:
        await db.execute(
            """INSERT INTO subjective_feedback
            (date, answer, answered_at, health_score, cultural_score,
             health_status, cultural_status)
            VALUES (?, ?, datetime('now'), ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                answer = excluded.answer,
                answered_at = excluded.answered_at""",
            (
                for_date,
                answer,
                scores["baseline_avg"],
                scores["cultural_pct"],
                scores["health_status"].value,
                scores["cultural_status"].value,
            ),
        )
        await db.commit()
    logger.info("Subjective feedback: recorded %s for %s", answer, for_date)
