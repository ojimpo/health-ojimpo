"""取得量が急減したソースについて、本人に「実際にやっていない/記録が壊れている」を聞く。

取得量の急減は、本物の活動低下と計測断のどちらでも同じ形になる。
Last.fm の 2026-07 の事故がまさにそれで、トークンは有効・ingestも成功・
レコードも存在し、データ上は「音楽を聴く量が98%減った」という正常な観測と
完全に一致していた。壊れていると分かったのは、本人が Last.fm の設定画面で
「Spotify連携が失効しています」のバナーを見たからだった。

つまりこの区別はデータからは原理的にできず、本人にしか判断できない。
自動で除外すると本物の低下を消してしまい、自動で除外しないと今回の
誤警報が続く。どちらも選べないので聞く。

回答が来るまでは何もしない（＝軸に残したまま）。判断がつかないうちに
勝手に外して「実は本当に減っていた」を見逃すより、警報が続く方が安全。
"""
import logging
from datetime import datetime, timedelta, timezone

from ..config import settings
from . import measurement_state
from .line_notify import reply_line_message, send_line_messages

logger = logging.getLogger(__name__)

POSTBACK_PREFIX = "ms:"

ACTION_BROKEN = "broken"
ACTION_REAL = "real"

# 同じソースについて聞き直すまでの間隔。答えない日が続いても毎週突かない。
ASK_INTERVAL_DAYS = 14


def _should_ask(asked_at: str | None, now: datetime) -> bool:
    if not asked_at:
        return True
    try:
        last = datetime.fromisoformat(asked_at).replace(tzinfo=timezone.utc)
    except ValueError:
        return True
    return now - last >= timedelta(days=ASK_INTERVAL_DAYS)


def build_question(source_id: str, name: str, detail: str) -> dict:
    """2択のQuick Reply付きメッセージを組む。"""
    return {
        "type": "text",
        "text": (
            f"「{name}」の記録が急減しています。\n{detail}\n\n"
            "実際にやっていないだけですか？ それとも記録が壊れていそうですか？"
        ),
        "quickReply": {
            "items": [
                {
                    "type": "action",
                    "action": {
                        "type": "postback",
                        "label": label,
                        "data": f"{POSTBACK_PREFIX}{action}:{source_id}",
                        "displayText": label,
                    },
                }
                for label, action in (
                    ("🙂 やってないだけ", ACTION_REAL),
                    ("🔧 記録が壊れてそう", ACTION_BROKEN),
                )
            ]
        },
    }


async def ask_about_collapses(report: list[dict], now: datetime | None = None) -> list[str]:
    """取得量が急減したソースについて本人に質問を送る。送った source_id を返す。

    既に broken と分かっているソースは聞かない（答えは出ている）。
    """
    if not settings.line_owner_user_id:
        logger.info("Measurement ask: LINE_OWNER_USER_ID not configured, skipping")
        return []
    if now is None:
        now = datetime.now(timezone.utc)

    broken = await measurement_state.get_broken_sources()
    asked: list[str] = []
    for r in report:
        source_id = r["id"]
        if not r.get("volume_collapse") or source_id in broken:
            continue
        if not _should_ask(await measurement_state.get_asked_at(source_id), now):
            continue
        await send_line_messages(
            settings.line_owner_user_id,
            [build_question(source_id, r["name"], r["detail"])],
        )
        await measurement_state.record_asked(source_id)
        asked.append(source_id)
        logger.info("Measurement ask: asked about %s", source_id)
    return asked


async def handle_postback_event(event: dict) -> None:
    """`ms:<action>:<source_id>` のpostbackを処理する（本人以外は無視）。"""
    user_id = (event.get("source") or {}).get("userId", "")
    if not user_id or user_id != settings.line_owner_user_id:
        logger.info("Measurement ask: postback from non-owner ignored")
        return

    data = (event.get("postback") or {}).get("data", "")
    parts = data.split(":", 2)
    if len(parts) != 3 or parts[0] != "ms" or not parts[2]:
        logger.info("Measurement ask: unknown postback data ignored: %s", data[:50])
        return
    action, source_id = parts[1], parts[2]

    if action == ACTION_BROKEN:
        await measurement_state.mark_broken(
            source_id, measurement_state.REASON_USER_REPORTED, "本人が記録の破損を申告"
        )
        message = (
            f"{source_id} をスコアから除外しました。\n"
            "記録が正常な量で戻れば自動で元に戻します。"
        )
    elif action == ACTION_REAL:
        # 「やってないだけ」＝観測として正しいので、低いまま軸に残す。
        # 過去に壊れている扱いにしていたなら、その判断を取り消す。
        await measurement_state.mark_ok(source_id)
        message = f"{source_id} はそのままスコアに反映します。"
    else:
        logger.info("Measurement ask: unknown action ignored: %s", action)
        return

    reply_token = event.get("replyToken")
    if reply_token:
        await reply_line_message(reply_token, message)
