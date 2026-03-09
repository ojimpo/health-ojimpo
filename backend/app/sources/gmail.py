import logging
from datetime import date, timedelta

import httpx

from ..database import get_db_context
from ..services.oauth import get_valid_token, has_token
from .base import SourceAdapter

logger = logging.getLogger(__name__)

GMAIL_API_BASE = "https://www.googleapis.com/gmail/v1"

# Search query for purchase confirmation emails
PURCHASE_QUERY = (
    "from:(auto-confirm@amazon.co.jp OR order-update@amazon.co.jp "
    "OR order@rakuten.co.jp OR noreply@rakuten.co.jp "
    "OR no-reply@mercari.jp)"
)


class GmailAdapter(SourceAdapter):
    source_id = "gmail"
    display_name = "Gmail (買い物)"

    async def is_configured(self) -> bool:
        return await has_token("gmail")

    async def fetch_and_store(self, from_date: str | None = None) -> tuple[int, int]:
        token = await get_valid_token("gmail")
        if not token:
            logger.warning("Gmail: no valid token")
            return 0, 0

        if not from_date:
            from_date = (date.today() - timedelta(days=30)).isoformat()

        headers = {"Authorization": f"Bearer {token}"}
        query = f"{PURCHASE_QUERY} after:{from_date.replace('-', '/')}"

        all_messages = []
        async with httpx.AsyncClient(timeout=30) as client:
            page_token = None
            while True:
                params = {"q": query, "maxResults": 100}
                if page_token:
                    params["pageToken"] = page_token

                try:
                    resp = await client.get(
                        f"{GMAIL_API_BASE}/users/me/messages",
                        headers=headers,
                        params=params,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                except Exception:
                    logger.exception("Failed to fetch Gmail messages")
                    break

                messages = data.get("messages", [])
                all_messages.extend(messages)
                page_token = data.get("nextPageToken")
                if not page_token:
                    break

            # Fetch message details for date and sender
            stored = 0
            for msg_ref in all_messages:
                msg_id = msg_ref["id"]
                try:
                    resp = await client.get(
                        f"{GMAIL_API_BASE}/users/me/messages/{msg_id}",
                        headers=headers,
                        params={"format": "metadata", "metadataHeaders": ["Date", "From", "Subject"]},
                    )
                    resp.raise_for_status()
                    msg = resp.json()
                except Exception:
                    continue

                headers_list = msg.get("payload", {}).get("headers", [])
                msg_date = ""
                sender = ""
                subject = ""
                for h in headers_list:
                    if h["name"] == "Date":
                        msg_date = h["value"]
                    elif h["name"] == "From":
                        sender = h["value"]
                    elif h["name"] == "Subject":
                        subject = h["value"]

                # Parse date to YYYY-MM-DD
                parsed_date = _parse_email_date(msg_date)
                if not parsed_date:
                    continue

                # Detect store
                store = "other"
                sender_lower = sender.lower()
                if "amazon" in sender_lower:
                    store = "amazon"
                elif "rakuten" in sender_lower:
                    store = "rakuten"
                elif "mercari" in sender_lower:
                    store = "mercari"

                async with get_db_context() as db:
                    await db.execute(
                        """INSERT OR IGNORE INTO gmail_purchases
                        (id, date, sender, subject, store)
                        VALUES (?, ?, ?, ?, ?)""",
                        (msg_id, parsed_date, sender, subject, store),
                    )
                    await db.commit()
                stored += 1

        logger.info("Gmail: stored %d purchase records", stored)
        return len(all_messages), stored

    async def aggregate(self) -> None:
        async with get_db_context() as db:
            await db.execute(
                """INSERT OR REPLACE INTO activity_records
                (date, source, category, minutes, raw_value, raw_unit, metadata)
                SELECT date, 'gmail', 'shopping', 0, COUNT(*), '回', NULL
                FROM gmail_purchases
                GROUP BY date"""
            )
            await db.commit()
        logger.info("Gmail aggregation completed")

    async def get_recent_activities(
        self, limit: int = 8, include_detail: bool = True
    ) -> list[dict]:
        async with get_db_context() as db:
            rows = await db.execute_fetchall(
                """SELECT date, COUNT(*) as cnt, GROUP_CONCAT(store, ', ') as stores
                FROM gmail_purchases
                GROUP BY date
                ORDER BY date DESC LIMIT ?""",
                (limit,),
            )

            activities = []
            today = date.today()
            for row in rows:
                d = date.fromisoformat(row[0])
                diff = (today - d).days
                time_str = "今日" if diff == 0 else "1日前" if diff == 1 else f"{diff}日前"

                activities.append({
                    "time": time_str,
                    "icon": "🛒",
                    "text": f"買い物 {row[1]}件",
                    "detail": row[2] if include_detail else None,
                    "color": "#8BE9FD",
                    "sort_date": row[0],
                })

            return activities


def _parse_email_date(date_str: str) -> str | None:
    """Parse email Date header to YYYY-MM-DD."""
    from email.utils import parsedate_to_datetime
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return None
