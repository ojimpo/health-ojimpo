"""LINEリッチメニュー/テキストコマンドによる手動トリガー（本人のみ）。

- ingest:run（またはテキスト「ingest」）: 全ソース取り込み+スコア再計算をバックグラウンド実行し、
  完了サマリをpushで返す
- menu:health: ソースヘルスレポートを即時作成してpush（週次レポートと同じ内容）
- menu:subjective: 主観フィードバックの3択質問を即時push（毎晩21時と同じもの）

LINE_OWNER_USER_ID 以外のuserIdは無視する（webhook自体は署名検証済み）。
"""
import asyncio
import logging
from datetime import datetime, timezone

from ..config import settings
from ..database import get_db_context
from .line_notify import reply_line_message, send_line_notification

logger = logging.getLogger(__name__)

POSTBACK_PREFIXES = ("ingest:", "menu:")
POSTBACK_RUN = "ingest:run"
MENU_HEALTH = "menu:health"
MENU_SUBJECTIVE = "menu:subjective"
MESSAGE_COMMANDS = {"ingest"}

_running = False


def is_ingest_command(text: str) -> bool:
    return text.strip().lower() in MESSAGE_COMMANDS


async def handle_command_event(event: dict) -> None:
    """リッチメニューのpostback/テキストコマンドをディスパッチする。"""
    user_id = (event.get("source") or {}).get("userId", "")
    if not user_id or user_id != settings.line_owner_user_id:
        logger.info("LINE menu: event from non-owner ignored")
        return

    data = (event.get("postback") or {}).get("data")
    if data is None or data == POSTBACK_RUN:
        await _start_ingest(event.get("replyToken"))
    elif data == MENU_HEALTH:
        await _start_health_report(event.get("replyToken"))
    elif data == MENU_SUBJECTIVE:
        from .subjective import send_daily_question

        await send_daily_question()
    else:
        logger.info("LINE menu: unknown postback data ignored: %s", data[:50])


# --- ingest ---


async def _start_ingest(reply_token: str | None) -> None:
    global _running
    if _running:
        if reply_token:
            await reply_line_message(reply_token, "⏳ ingest実行中です。完了通知を待ってください")
        return

    _running = True
    if reply_token:
        try:
            await reply_line_message(reply_token, "▶ 全ソースのingestを開始しました。完了したら通知します")
        except Exception:
            logger.exception("LINE menu: ingest reply failed")
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


# --- source health report ---


async def _start_health_report(reply_token: str | None) -> None:
    """OAuthトークンの実refreshを含み数十秒かかりうるのでバックグラウンドで実行する。"""
    if reply_token:
        try:
            await reply_line_message(reply_token, "🩺 ヘルスチェック中です。結果を送ります")
        except Exception:
            logger.exception("LINE menu: health reply failed")
    asyncio.create_task(_health_report_task())


async def _health_report_task() -> None:
    try:
        from .source_health import send_weekly_report

        await send_weekly_report()
    except Exception:
        logger.exception("LINE menu: health report failed")
        try:
            await send_line_notification(
                settings.line_owner_user_id,
                "⚠ ヘルスレポートの作成中にエラーが発生しました。ログを確認してください",
            )
        except Exception:
            logger.exception("LINE menu: health failure notification failed")
