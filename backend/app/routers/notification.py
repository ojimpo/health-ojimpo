import hashlib
import hmac
import logging
import uuid
from base64 import b64encode
from datetime import datetime, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from ..config import settings
from ..database import get_db_context
from ..models.schemas import EmailSubscribeRequest
from ..services.email_notify import send_verification_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notification", tags=["notification"])


# --- Email subscription ---


@router.post("/subscribe/email")
async def subscribe_email(req: EmailSubscribeRequest):
    """Register an email for notifications. Sends a verification email."""
    email = req.email.strip().lower()

    async with get_db_context() as db:
        # Check if already registered
        rows = await db.execute_fetchall(
            "SELECT id, verified, active FROM notification_subscribers WHERE channel = 'email' AND channel_id = ?",
            (email,),
        )
        if rows:
            sub = rows[0]
            if sub[1] and sub[2]:  # verified and active
                return {"message": "このメールアドレスは既に登録済みです"}
            # Re-activate or re-verify
            if sub[1] and not sub[2]:
                await db.execute(
                    "UPDATE notification_subscribers SET active = 1, updated_at = datetime('now') WHERE id = ?",
                    (sub[0],),
                )
                await db.commit()
                return {"message": "通知を再開しました"}

        # Generate verification token
        token = uuid.uuid4().hex
        expires = (datetime.utcnow() + timedelta(hours=24)).isoformat()

        await db.execute(
            """INSERT INTO notification_subscribers (channel, channel_id, verified, verification_token, verification_expires_at)
            VALUES ('email', ?, 0, ?, ?)
            ON CONFLICT(channel, channel_id) DO UPDATE SET
                verification_token = ?, verification_expires_at = ?, active = 1, updated_at = datetime('now')""",
            (email, token, expires, token, expires),
        )
        await db.commit()

    # Send verification email
    verify_url = f"https://{settings.app_domain}/api/notification/verify/{token}"
    try:
        await send_verification_email(email, verify_url)
    except Exception:
        logger.exception("Failed to send verification email to %s", email)
        return JSONResponse(
            status_code=500,
            content={"message": "確認メールの送信に失敗しました。しばらく後にお試しください"},
        )

    return {"message": "確認メールを送信しました"}


@router.get("/verify/{token}")
async def verify_email(token: str):
    """Verify an email subscription via token link."""
    async with get_db_context() as db:
        rows = await db.execute_fetchall(
            "SELECT id, verification_expires_at FROM notification_subscribers WHERE verification_token = ?",
            (token,),
        )
        if not rows:
            return HTMLResponse(
                content=_result_html("リンクが無効です", False), status_code=404
            )

        sub_id = rows[0][0]
        expires = rows[0][1]
        if expires and datetime.fromisoformat(expires) < datetime.utcnow():
            return HTMLResponse(
                content=_result_html("リンクの有効期限が切れています", False), status_code=400
            )

        await db.execute(
            """UPDATE notification_subscribers
            SET verified = 1, verification_token = NULL, verification_expires_at = NULL, updated_at = datetime('now')
            WHERE id = ?""",
            (sub_id,),
        )
        await db.commit()

    return HTMLResponse(content=_result_html("通知の登録が完了しました", True))


@router.get("/unsubscribe/{subscriber_id}")
async def unsubscribe(subscriber_id: int):
    """Unsubscribe from notifications."""
    async with get_db_context() as db:
        rows = await db.execute_fetchall(
            "SELECT id FROM notification_subscribers WHERE id = ?",
            (subscriber_id,),
        )
        if not rows:
            return HTMLResponse(
                content=_result_html("登録が見つかりません", False), status_code=404
            )

        await db.execute(
            "UPDATE notification_subscribers SET active = 0, updated_at = datetime('now') WHERE id = ?",
            (subscriber_id,),
        )
        await db.commit()

    return HTMLResponse(content=_result_html("配信を停止しました", True))


# --- LINE webhook ---


@router.post("/line/webhook")
async def line_webhook(request: Request):
    """Receive LINE Messaging API webhook events (follow/unfollow)."""
    body = await request.body()

    # Verify signature
    channel_secret = settings.line_channel_secret
    if channel_secret:
        signature = request.headers.get("X-Line-Signature", "")
        expected = b64encode(
            hmac.new(channel_secret.encode(), body, hashlib.sha256).digest()
        ).decode()
        if signature != expected:
            return JSONResponse(status_code=403, content={"error": "Invalid signature"})

    import json
    data = json.loads(body)
    events = data.get("events", [])

    async with get_db_context() as db:
        for event in events:
            event_type = event.get("type")
            user_id = event.get("source", {}).get("userId")
            if not user_id:
                continue

            if event_type == "follow":
                # Get display name via profile API
                display_name = None
                if settings.line_channel_access_token:
                    import httpx
                    try:
                        async with httpx.AsyncClient(timeout=10) as client:
                            resp = await client.get(
                                f"https://api.line.me/v2/bot/profile/{user_id}",
                                headers={"Authorization": f"Bearer {settings.line_channel_access_token}"},
                            )
                            if resp.status_code == 200:
                                display_name = resp.json().get("displayName")
                    except Exception:
                        pass

                await db.execute(
                    """INSERT INTO notification_subscribers (channel, channel_id, display_name, verified)
                    VALUES ('line', ?, ?, 1)
                    ON CONFLICT(channel, channel_id) DO UPDATE SET
                        active = 1, display_name = ?, updated_at = datetime('now')""",
                    (user_id, display_name, display_name),
                )
                logger.info("LINE follow: %s (%s)", user_id[:8] + "...", display_name)

            elif event_type == "unfollow":
                await db.execute(
                    "UPDATE notification_subscribers SET active = 0, updated_at = datetime('now') WHERE channel = 'line' AND channel_id = ?",
                    (user_id,),
                )
                logger.info("LINE unfollow: %s", user_id[:8] + "...")

        await db.commit()

    return {"status": "ok"}


@router.get("/line/info")
async def line_info():
    """Return LINE official account info for QR code display."""
    bot_id = settings.line_bot_basic_id
    if not bot_id:
        return {"available": False}
    return {
        "available": True,
        "bot_basic_id": bot_id,
        "add_friend_url": f"https://line.me/R/ti/p/{bot_id}",
    }


# --- Admin endpoints ---


@router.get("/subscribers")
async def list_subscribers():
    """List all notification subscribers (admin)."""
    async with get_db_context() as db:
        rows = await db.execute_fetchall(
            """SELECT id, channel, channel_id, display_name, verified, active, created_at
            FROM notification_subscribers ORDER BY created_at DESC"""
        )
    return [
        {
            "id": r[0], "channel": r[1], "channel_id": r[2],
            "display_name": r[3], "verified": bool(r[4]),
            "active": bool(r[5]), "created_at": r[6],
        }
        for r in rows
    ]


@router.delete("/subscribers/{subscriber_id}")
async def delete_subscriber(subscriber_id: int):
    """Delete a subscriber (admin)."""
    async with get_db_context() as db:
        await db.execute(
            "DELETE FROM notification_subscribers WHERE id = ?", (subscriber_id,)
        )
        await db.commit()
    return {"status": "deleted"}


# --- Helper ---


def _result_html(message: str, success: bool) -> str:
    color = "#00F0FF" if success else "#FF3366"
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#07080F;color:#E0E0E0;font-family:'Courier New',monospace;display:flex;justify-content:center;align-items:center;min-height:100vh;">
<div style="text-align:center;padding:32px;">
<div style="font-size:10px;letter-spacing:3px;color:rgba(255,255,255,0.35);margin-bottom:24px;">HEALTH.OJIMPO.COM</div>
<div style="font-size:16px;color:{color};margin-bottom:16px;">{message}</div>
<a href="https://{settings.app_domain}" style="font-size:11px;color:rgba(255,255,255,0.3);text-decoration:none;">ダッシュボードに戻る</a>
</div>
</body>
</html>"""
