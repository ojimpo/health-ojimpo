import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from ..config import settings as app_settings
from ..database import get_db_context
from ..models.schemas import IngestStatusResponse, IngestTrigger
from ..scheduler import get_next_run_time
from ..services.ingest import run_ingest_pipeline
from ..sources.registry import get_adapter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingest", tags=["ingest"])

# In-memory storage for app open timestamps (source -> timestamp)
_app_open_times: dict[str, datetime] = {}


class WebhookEntry(BaseModel):
    source: str
    date: str
    minutes: float


class WebhookPayload(BaseModel):
    """単一 or バッチ送信対応。entries がある場合はバッチ、なければ単一。"""
    # 単一送信用
    source: str | None = None
    date: str | None = None
    minutes: float | None = None
    # バッチ送信用
    entries: list[WebhookEntry] | None = None
    # app open/close 用
    action: str | None = None


def _verify_webhook_token(authorization: str | None):
    """Bearer トークンを検証。WEBHOOK_SECRET未設定なら認証スキップ。"""
    secret = app_settings.webhook_secret
    if not secret:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid Authorization header")
    token = authorization[7:]
    if token != secret:
        raise HTTPException(403, "Invalid webhook token")


async def _store_one(source: str, date_str: str, minutes: float) -> dict:
    """Webhook1件分を保存。"""
    adapter = get_adapter(source)
    if not adapter:
        raise HTTPException(400, f"Unknown source: {source}")

    if not hasattr(adapter, "store_webhook_data"):
        raise HTTPException(400, f"Source {source} does not support webhook data")

    await adapter.store_webhook_data(date_str, minutes)
    await adapter.aggregate()

    async with get_db_context() as db:
        await db.execute(
            "UPDATE source_settings SET status = 'active' WHERE id = ? AND status = 'coming_soon'",
            (source,),
        )
        await db.commit()

    return {"source": source, "date": date_str, "minutes": minutes}


@router.post(
    "/trigger",
    summary="データ取得手動トリガー",
    description="指定ソースからデータを手動取得する。from_dateで開始日を指定可能。",
)
async def trigger_ingest(body: IngestTrigger):
    adapter = get_adapter(body.source)
    if not adapter:
        raise HTTPException(400, f"Unknown source: {body.source}")
    asyncio.create_task(run_ingest_pipeline(source_id=body.source, from_date=body.from_date))
    return {"status": "started", "source": body.source}


@router.post(
    "/webhook",
    summary="Webhook受信 (iOS Shortcut等)",
    description="スクリーンタイム等のデータをWebhookで受信。単一・バッチ両対応。Bearer認証。",
)
async def receive_webhook(
    body: WebhookPayload,
    authorization: str | None = Header(default=None),
):
    _verify_webhook_token(authorization)

    # バッチ送信
    if body.entries:
        results = []
        for entry in body.entries:
            result = await _store_one(entry.source, entry.date, entry.minutes)
            results.append(result)
        return {"status": "stored", "count": len(results), "results": results}

    # app open/close（iOS Shortcut用）
    if body.source and body.action:
        if body.action == "open":
            _app_open_times[body.source] = datetime.now(timezone.utc)
            logger.info(f"App open recorded: {body.source}")
            return {"status": "recorded", "source": body.source, "action": "open"}
        elif body.action == "close":
            logger.info(f"App close received: {body.source}")
            start = _app_open_times.pop(body.source, None)
            if not start:
                logger.info(f"App close skipped (no open): {body.source}")
                return {"status": "skipped", "source": body.source, "reason": "no open event"}
            elapsed = (datetime.now(timezone.utc) - start).total_seconds() / 60.0
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            result = await _store_one(body.source, today, round(elapsed, 1))
            return {"status": "stored", **result, "elapsed_minutes": round(elapsed, 1)}
        else:
            raise HTTPException(400, f"Unknown action: {body.action}. Use 'open' or 'close'.")

    # 単一送信
    if body.source and body.date is not None and body.minutes is not None:
        result = await _store_one(body.source, body.date, body.minutes)
        return {"status": "stored", **result}

    raise HTTPException(400, "Provide source/date/minutes, entries[], or source/action")


class ClaudeSessionPayload(BaseModel):
    """Claude Codeのフックから送られてくる日次作業分数。"""
    date: str  # YYYY-MM-DD（端末ローカル日付）
    minutes: float  # 当日の累積作業分数
    host: str  # クライアント識別子（hostname推奨）


@router.post(
    "/webhook/claude_session",
    summary="Claude Code 作業時間を受信",
    description="各端末のStopフックから送信される日次作業分数。host単位で記録し、aggregateで合算。Bearer認証。",
)
async def receive_claude_session(
    body: ClaudeSessionPayload,
    authorization: str | None = Header(default=None),
):
    _verify_webhook_token(authorization)

    adapter = get_adapter("claude")
    if not adapter:
        raise HTTPException(500, "claude adapter not registered")

    await adapter.store_webhook_data(body.date, body.minutes, body.host)
    await adapter.aggregate()

    return {
        "status": "stored",
        "source": "claude",
        "date": body.date,
        "host": body.host,
        "minutes": body.minutes,
    }


@router.get(
    "/status",
    response_model=IngestStatusResponse,
    summary="取得状況確認",
)
async def get_ingest_status():
    async with get_db_context() as db:
        last_run = await db.execute_fetchall(
            "SELECT completed_at, status FROM ingest_log ORDER BY id DESC LIMIT 1"
        )
        total = await db.execute_fetchall(
            "SELECT COUNT(*) FROM activity_records"
        )
        return {
            "last_run": last_run[0][0] if last_run else None,
            "records_total": total[0][0],
            "status": last_run[0][1] if last_run else "never",
            "next_scheduled": get_next_run_time(),
        }
