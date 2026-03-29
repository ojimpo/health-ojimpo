import base64
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx

from ..config import settings
from .oauth import get_valid_token

logger = logging.getLogger(__name__)

GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"


async def send_email_notification(to_email: str, subject: str, body_html: str) -> None:
    """Send an email via Gmail API."""
    token = await get_valid_token("gmail")
    if not token:
        raise RuntimeError("Gmail OAuth token not available — re-authorize at /api/oauth/gmail/authorize")

    msg = MIMEMultipart("alternative")
    msg["To"] = to_email
    msg["From"] = f"health.ojimpo.com <{settings.app_username}@gmail.com>"
    msg["Subject"] = subject
    msg.attach(MIMEText(body_html, "html", "utf-8"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            GMAIL_SEND_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={"raw": raw},
        )
        if resp.status_code not in (200, 202):
            logger.error("Gmail send failed: %d %s", resp.status_code, resp.text)
            resp.raise_for_status()

    logger.info("Email notification sent to %s", to_email)


async def send_verification_email(to_email: str, verify_url: str) -> None:
    """Send a verification email for new email subscribers."""
    subject = "[health.ojimpo.com] メール通知の登録確認"
    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#07080F;color:#E0E0E0;font-family:'Courier New',monospace;">
<div style="max-width:500px;margin:0 auto;padding:32px 24px;">
<div style="font-size:10px;letter-spacing:3px;color:rgba(255,255,255,0.35);margin-bottom:24px;">HEALTH.OJIMPO.COM</div>
<div style="font-size:13px;line-height:1.8;margin-bottom:24px;">
コンディション通知の登録を確認するため、以下のリンクをクリックしてください。
</div>
<div style="margin-bottom:24px;">
<a href="{verify_url}" style="display:inline-block;padding:10px 24px;background:rgba(0,240,255,0.08);border:1px solid rgba(0,240,255,0.3);border-radius:6px;color:#00F0FF;text-decoration:none;font-size:12px;letter-spacing:2px;">CONFIRM</a>
</div>
<div style="font-size:10px;color:rgba(255,255,255,0.2);">
このリンクは24時間有効です。心当たりがない場合は無視してください。
</div>
</div>
</body>
</html>"""

    await send_email_notification(to_email, subject, html)
