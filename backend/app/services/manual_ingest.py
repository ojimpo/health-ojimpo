"""LINEからの手動ingestトリガー。

リッチメニューのpostback（ingest:run）またはテキスト「ingest」で、
全ソースの取り込み+スコア再計算をバックグラウンド実行し、完了サマリをpushで返す。
LINE_OWNER_USER_ID 以外のuserIdは無視する（webhook自体は署名検証済み）。
"""
import asyncio
import logging
from datetime import datetime, timezone

from ..config import settings
from ..database import get_db_context
from .line_notify import reply_line_message, send_line_notification

logger = logging.getLogger(__name__)

POSTBACK_PREFIX = "ingest:"
POSTBACK_RUN = "ingest:run"
MESSAGE_COMMANDS = {"ingest"}

_running = False


def is_ingest_command(text: str) -> bool:
    return text.strip().lower() in MESSAGE_COMMANDS


async def handle_ingest_event(event: dict) -> None:
    """postback(ingest:run) またはテキストコマンドから全ソースingestを起動する。"""
    global _running
    user_id = (event.get("source") or {}).get("userId", "")
    if not user_id or user_id != settings.line_owner_user_id:
        logger.info("Manual ingest: event from non-owner ignored")
        return

    data = (event.get("postback") or {}).get("data")
    if data is not None and data != POSTBACK_RUN:
        logger.info("Manual ingest: unknown postback data ignored: %s", data[:50])
        return

    reply_token = event.get("replyToken")
    if _running:
        if reply_token:
            await reply_line_message(reply_token, "⏳ ingest実行中です。完了通知を待ってください")
        return

    _running = True
    if reply_token:
        try:
            await reply_line_message(reply_token, "▶ 全ソースのingestを開始しました。完了したら通知します")
        except Exception:
            logger.exception("Manual ingest: reply failed")
    asyncio.create_task(_run_and_report())


async def _run_and_report() -> None:
    global _running
    started_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    try:
        from .ingest import run_all_ingest

        await run_all_ingest()
        summary = await _build_summary(started_at)
        await send_line_notification(settings.line_owner_user_id, summary)
        logger.info("Manual ingest: completed")
    except Exception:
        logger.exception("Manual ingest: run failed")
        try:
            await send_line_notification(
                settings.line_owner_user_id,
                "⚠ ingestの実行中にエラーが発生しました。ログを確認してください",
            )
        except Exception:
            logger.exception("Manual ingest: failure notification failed")
    finally:
        _running = False


async def _build_summary(started_at: str) -> str:
    async with get_db_context() as db:
        rows = await db.execute_fetchall(
            "SELECT source, status FROM ingest_log WHERE started_at >= ? ORDER BY id",
            (started_at,),
        )
    completed = [r[0] for r in rows if r[1] == "completed"]
    failed = [r[0] for r in rows if r[1] == "failed"]
    lines = [f"✅ ingest完了: {len(completed)}ソース成功"]
    if failed:
        lines.append(f"⚠ 失敗: {', '.join(failed)}")
    return "\n".join(lines)
