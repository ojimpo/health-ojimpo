"""写真カテゴリの2ソース。

- immich_photos: Immich の検索統計APIで「iPhoneで撮った写真」を日次カウント。
  make=Apple + type=IMAGE で絞るため、EXIFにカメラ情報を持たないスクリーンショットや
  保存画像は自然に除外される。X-E5 は make=FUJIFILM なので二重計上しない。
- photo_genka: photo-genka (x-e5.ojimpo.com) の /api/daily-shots から X-E5 の
  日次撮影枚数を取得。分母はカメラ内シャッターカウンタ(ImageCount)の日次差分なので、
  Immich に取り込んでいない・カメラ内で削除した分も撮影行為として数えられる。
"""
import logging
from datetime import date, datetime, timedelta, timezone

import httpx

from ..config import settings
from ..database import get_db_context
from .base import SourceAdapter, format_relative_day

logger = logging.getLogger(__name__)

JST = timezone(timedelta(hours=9))


class ImmichPhotosAdapter(SourceAdapter):
    source_id = "immich_photos"
    display_name = "写真 (iPhone)"

    # 通常フェッチで遡る日数（decayの裾が伸びる分より少し長め）
    LOOKBACK_DAYS = 14

    async def is_configured(self) -> bool:
        return bool(settings.immich_api_url and settings.immich_api_key)

    async def _count_day(self, client: httpx.AsyncClient, d: date) -> int:
        resp = await client.post(
            "/api/search/statistics",
            json={
                "takenAfter": f"{d.isoformat()}T00:00:00+09:00",
                "takenBefore": f"{d.isoformat()}T23:59:59+09:00",
                "type": "IMAGE",
                "make": "Apple",
            },
        )
        resp.raise_for_status()
        return int(resp.json().get("total") or 0)

    async def fetch_and_store(self, from_date: str | None = None) -> tuple[int, int]:
        today = datetime.now(JST).date()
        start = (
            date.fromisoformat(from_date)
            if from_date
            else today - timedelta(days=self.LOOKBACK_DAYS)
        )

        daily: dict[str, int] = {}
        async with httpx.AsyncClient(
            base_url=settings.immich_api_url.rstrip("/"),
            headers={"x-api-key": settings.immich_api_key},
            timeout=30,
        ) as client:
            d = start
            while d <= today:
                daily[d.isoformat()] = await self._count_day(client, d)
                d += timedelta(days=1)

        stored = 0
        async with get_db_context() as db:
            for day, count in daily.items():
                if count <= 0:
                    # 0枚の日は行を持たない（event分類なのでゼロは正常）
                    await db.execute(
                        "DELETE FROM activity_records WHERE date = ? AND source = 'immich_photos'",
                        (day,),
                    )
                    continue
                await db.execute(
                    """INSERT OR REPLACE INTO activity_records
                    (date, source, category, minutes, raw_value, raw_unit, metadata)
                    VALUES (?, 'immich_photos', 'photo', ?, ?, '枚', NULL)""",
                    (day, count, count),
                )
                stored += 1
            await db.commit()

        logger.info("immich_photos: stored %d daily records", stored)
        return sum(daily.values()), stored

    async def aggregate(self) -> None:
        pass

    async def get_recent_activities(
        self, limit: int = 8, include_detail: bool = True
    ) -> list[dict]:
        return await _photo_feed(
            "immich_photos", "📱", "iPhoneで{count}枚撮影", "#A2AAAD", limit
        )


class PhotoGenkaAdapter(SourceAdapter):
    source_id = "photo_genka"
    display_name = "カメラ (X-E5)"

    async def is_configured(self) -> bool:
        return bool(settings.photo_genka_api_url)

    async def fetch_and_store(self, from_date: str | None = None) -> tuple[int, int]:
        base_url = settings.photo_genka_api_url.rstrip("/")
        params = {"since": from_date} if from_date else {}
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{base_url}/api/daily-shots", params=params)
            resp.raise_for_status()
            rows = resp.json()

        stored = 0
        async with get_db_context() as db:
            for row in rows:
                shots = int(row.get("shots") or 0)
                if shots <= 0:
                    continue
                await db.execute(
                    """INSERT OR REPLACE INTO activity_records
                    (date, source, category, minutes, raw_value, raw_unit, metadata)
                    VALUES (?, 'photo_genka', 'photo', ?, ?, '枚', NULL)""",
                    (row["day"], shots, shots),
                )
                stored += 1
            await db.commit()

        logger.info("photo_genka: stored %d daily records from %d days", stored, len(rows))
        return len(rows), stored

    async def aggregate(self) -> None:
        pass

    async def get_recent_activities(
        self, limit: int = 8, include_detail: bool = True
    ) -> list[dict]:
        return await _photo_feed(
            "photo_genka", "📷", "X-E5で{count}枚撮影", "#01916D", limit
        )


async def _photo_feed(
    source: str, icon: str, text_tmpl: str, color: str, limit: int
) -> list[dict]:
    async with get_db_context() as db:
        rows = await db.execute_fetchall(
            """SELECT date, raw_value FROM activity_records
            WHERE source = ? ORDER BY date DESC LIMIT ?""",
            (source, limit),
        )

    today = date.today()
    return [
        {
            "time": format_relative_day(date.fromisoformat(row[0]), today),
            "icon": icon,
            "text": text_tmpl.format(count=int(row[1])),
            "detail": None,
            "color": color,
            "sort_date": row[0],
        }
        for row in rows
    ]
