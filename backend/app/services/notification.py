import json
import logging
from datetime import datetime, timedelta

from ..config import settings
from ..database import get_db_context
from ..models.enums import CulturalStatus, HealthStatus
from .scoring import calculate_scores

logger = logging.getLogger(__name__)


def _detect_transitions(
    prev_health: str,
    prev_cultural: str,
    curr_health: HealthStatus,
    curr_cultural: CulturalStatus,
) -> list[str]:
    """Detect status transitions that should trigger notifications.

    Health: any downward transition (NORMAL→CAUTION, NORMAL→CRITICAL, CAUTION→CRITICAL)
    Cultural: only transitions to LOW (RICH→LOW, MODERATE→LOW). RICH→MODERATE is silent.
    """
    transitions = []
    health_order = {"NORMAL": 0, "CAUTION": 1, "CRITICAL": 2}
    cultural_order = {"RICH": 0, "MODERATE": 1, "LOW": 2}

    curr_h = curr_health.value
    curr_c = curr_cultural.value

    if health_order.get(curr_h, 0) > health_order.get(prev_health, 0):
        transitions.append(f"health:{prev_health}->{curr_h}")

    # Cultural: only notify when entering LOW
    if curr_c == "LOW" and cultural_order.get(prev_cultural, 0) < cultural_order.get("LOW", 2):
        transitions.append(f"cultural:{prev_cultural}->{curr_c}")

    return transitions


def build_notification_message(
    transitions: list[str],
    health_status: str,
    health_score: float,
    cultural_status: str,
    cultural_score: float,
) -> str:
    """Build LINE notification message text."""
    has_health = any(t.startswith("health:") for t in transitions)
    has_cultural = any(t.startswith("cultural:") for t in transitions)
    is_critical = health_status == "CRITICAL"

    personal_line = settings.personal_line_url

    if has_health and has_cultural:
        # Both deteriorated
        if is_critical:
            lines = [
                f"\U0001f6a8 [health.ojimpo.com]",
                f"健康スコアと文化的活動の両方が大きく低下しています",
                f"健康: {health_status} ({health_score:.0f}) / 文化: {cultural_status} ({cultural_score:.0f})",
                f"生存確認してあげてください",
                f"https://health.ojimpo.com",
            ]
        else:
            lines = [
                f"\u26a0\ufe0f [health.ojimpo.com]",
                f"健康スコアと文化的活動の両方が低下しています",
                f"健康: {health_status} ({health_score:.0f}) / 文化: {cultural_status} ({cultural_score:.0f})",
                f"声をかけてあげてください",
                f"https://health.ojimpo.com",
            ]
        if is_critical and personal_line:
            lines.append(f"\nLINE: {personal_line}")
        return "\n".join(lines)

    if has_health:
        if is_critical:
            lines = [
                f"\u26a0\ufe0f [health.ojimpo.com]",
                f"健康スコアが大きく低下しています ({health_status}: {health_score:.0f})",
                f"連絡を取ってみてください",
                f"https://health.ojimpo.com",
            ]
            if personal_line:
                lines.append(f"\nLINE: {personal_line}")
        else:
            lines = [
                f"[health.ojimpo.com]",
                f"健康スコアが低下しています ({health_status}: {health_score:.0f})",
                f"少し気にかけてあげてください",
                f"https://health.ojimpo.com",
            ]
        return "\n".join(lines)

    # Cultural LOW
    lines = [
        f"[health.ojimpo.com]",
        f"文化的活動が減少しています ({cultural_status}: {cultural_score:.0f})",
        f"忙しいのかもしれません — 息抜きに誘ってあげてください",
        f"https://health.ojimpo.com",
    ]
    return "\n".join(lines)


def build_email_html(
    transitions: list[str],
    health_status: str,
    health_score: float,
    cultural_status: str,
    cultural_score: float,
    unsubscribe_url: str,
) -> tuple[str, str]:
    """Build email subject and HTML body. Returns (subject, html)."""
    text = build_notification_message(
        transitions, health_status, health_score, cultural_status, cultural_score
    )
    subject = "[health.ojimpo.com] コンディション変化のお知らせ"

    # Status colors
    status_colors = {
        "NORMAL": "#50FA7B", "CAUTION": "#FFB86C", "CRITICAL": "#FF1744",
        "RICH": "#00F0FF", "MODERATE": "#FFB86C", "LOW": "#FF3366",
    }
    h_color = status_colors.get(health_status, "#E0E0E0")
    c_color = status_colors.get(cultural_status, "#E0E0E0")

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#07080F;color:#E0E0E0;font-family:'Courier New',monospace;">
<div style="max-width:500px;margin:0 auto;padding:32px 24px;">
<div style="font-size:10px;letter-spacing:3px;color:rgba(255,255,255,0.35);margin-bottom:24px;">HEALTH.OJIMPO.COM</div>
<table cellpadding="0" cellspacing="0" style="width:100%;border:1px solid rgba(255,255,255,0.06);border-radius:14px;margin-bottom:20px;">
<tr>
<td style="padding:20px;width:50%;vertical-align:top;">
<div style="font-size:10px;color:rgba(255,255,255,0.35);margin-bottom:4px;">HEALTH</div>
<div style="font-size:20px;font-weight:bold;color:{h_color};margin-bottom:4px;">{health_status}</div>
<div style="font-size:12px;color:rgba(255,255,255,0.5);">Score: {health_score:.0f}</div>
</td>
<td style="padding:20px;width:50%;vertical-align:top;">
<div style="font-size:10px;color:rgba(255,255,255,0.35);margin-bottom:4px;">CULTURAL</div>
<div style="font-size:20px;font-weight:bold;color:{c_color};margin-bottom:4px;">{cultural_status}</div>
<div style="font-size:12px;color:rgba(255,255,255,0.5);">Score: {cultural_score:.0f}</div>
</td>
</tr>
</table>
<div style="font-size:13px;line-height:1.8;white-space:pre-wrap;margin-bottom:24px;">{text}</div>
<div style="font-size:11px;color:rgba(255,255,255,0.35);margin-bottom:24px;line-height:1.6;">LINEまたはこのメールへの返信で連絡を取ることができます。</div>
<div style="border-top:1px solid rgba(255,255,255,0.06);padding-top:16px;font-size:10px;color:rgba(255,255,255,0.2);">
<a href="{unsubscribe_url}" style="color:rgba(255,255,255,0.3);">配信停止</a>
</div>
</div>
</body>
</html>"""

    return subject, html


async def check_and_notify() -> None:
    """Check for status transitions and send notifications if needed.

    Called after each ingest batch completes.
    """
    if not settings.notification_enabled:
        return

    scores = await calculate_scores()
    curr_health = scores["health_status"]
    curr_cultural = scores["cultural_status"]
    health_score = scores["baseline_avg"]
    cultural_score = scores["cultural_pct"]

    # Get previous snapshot
    async with get_db_context() as db:
        rows = await db.execute_fetchall(
            "SELECT health_status, cultural_status FROM status_snapshot WHERE id = 1"
        )
        if rows:
            prev_health = rows[0][0]
            prev_cultural = rows[0][1]
        else:
            prev_health = "NORMAL"
            prev_cultural = "RICH"

        # Always update snapshot
        await db.execute(
            """INSERT OR REPLACE INTO status_snapshot
            (id, health_status, cultural_status, health_score, cultural_score, updated_at)
            VALUES (1, ?, ?, ?, ?, datetime('now'))""",
            (curr_health.value, curr_cultural.value, health_score, cultural_score),
        )
        await db.commit()

    transitions = _detect_transitions(prev_health, prev_cultural, curr_health, curr_cultural)
    if not transitions:
        logger.info("No status transitions detected, skipping notification")
        return

    # Cooldown: skip if last notification was within 1 hour
    async with get_db_context() as db:
        rows = await db.execute_fetchall(
            "SELECT triggered_at FROM notification_log ORDER BY id DESC LIMIT 1"
        )
        if rows:
            last_sent = datetime.fromisoformat(rows[0][0])
            if datetime.utcnow() - last_sent < timedelta(hours=1):
                logger.info("Cooldown active, skipping notification (last sent: %s)", last_sent)
                return

    logger.info("Status transitions detected: %s", transitions)
    await send_notifications(
        transitions, curr_health.value, health_score, curr_cultural.value, cultural_score
    )


async def send_notifications(
    transitions: list[str],
    health_status: str,
    health_score: float,
    cultural_status: str,
    cultural_score: float,
) -> None:
    """Send notifications to all active, verified subscribers."""
    from .email_notify import send_email_notification
    from .line_notify import send_line_notification

    async with get_db_context() as db:
        rows = await db.execute_fetchall(
            "SELECT id, channel, channel_id FROM notification_subscribers WHERE active = 1 AND verified = 1"
        )

    if not rows:
        logger.info("No active subscribers, skipping notification")
        return

    message = build_notification_message(
        transitions, health_status, health_score, cultural_status, cultural_score
    )

    notified = 0
    errors = []

    for row in rows:
        sub_id, channel, channel_id = row[0], row[1], row[2]
        try:
            if channel == "line":
                await send_line_notification(channel_id, message)
                notified += 1
            elif channel == "email":
                unsubscribe_url = f"https://{settings.app_domain}/api/notification/unsubscribe/{sub_id}"
                subject, html = build_email_html(
                    transitions, health_status, health_score, cultural_status, cultural_score,
                    unsubscribe_url,
                )
                await send_email_notification(channel_id, subject, html)
                notified += 1
        except Exception as e:
            logger.exception("Failed to notify subscriber %d (%s)", sub_id, channel)
            errors.append({"subscriber_id": sub_id, "channel": channel, "error": str(e)})

    # Log notification
    transition_str = ", ".join(transitions)
    async with get_db_context() as db:
        await db.execute(
            """INSERT INTO notification_log
            (health_status, cultural_status, transition_type, subscribers_notified, errors)
            VALUES (?, ?, ?, ?, ?)""",
            (
                health_status,
                cultural_status,
                transition_str,
                notified,
                json.dumps(errors) if errors else None,
            ),
        )
        await db.commit()

    logger.info(
        "Notifications sent: %d/%d (transitions: %s)", notified, len(rows), transition_str
    )
