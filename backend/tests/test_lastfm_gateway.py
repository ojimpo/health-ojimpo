"""Last.fm アダプタが scrobble-gateway の日次件数を正しく取り込むことのテスト。

2026-10-05 に Last.fm の取り込みを scrobble-gateway に一本化した。health-ojimpo は
日ごとの件数（UTC）だけを受け取る。守るべき性質:
- 取り直す窓の中は丸ごと置き換える（gateway が返さない日は 0 件）。窓の外は触らない
- gateway の全件取得が終わる前の値では上書きしない
- 日次の再生時間は「件数 × 既定の曲長」で、旧実装と同じ値になる
"""
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.config import settings
from app.database import get_db_context
from app.sources import lastfm as lastfm_source
from app.sources.lastfm import LastfmAdapter


@pytest.fixture
def gateway(monkeypatch):
    """scrobble-gateway の /daily-plays を差し替える。受けたクエリを記録する。"""
    state = {"days": [], "fullHistorySynced": True, "newest": "2026-10-04T12:54:05.000Z", "queries": []}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/daily-plays"
        state["queries"].append(dict(request.url.params))
        return httpx.Response(200, text=json.dumps({
            "timezone": "UTC",
            "days": state["days"],
            "newestScrobbleAt": state["newest"],
            "fullHistorySynced": state["fullHistorySynced"],
        }))

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        lastfm_source.httpx, "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    monkeypatch.setattr(settings, "scrobble_gateway_url", "http://scrobble-gateway:3001")
    return state


async def _daily() -> dict[str, int]:
    async with get_db_context() as db:
        rows = await db.execute_fetchall("SELECT date, plays FROM lastfm_daily_plays")
    return {r[0]: r[1] for r in rows}


def _day(offset: int) -> str:
    return (datetime.now(timezone.utc).date() - timedelta(days=offset)).isoformat()


async def test_replaces_the_window_and_leaves_older_days(test_db, gateway):
    async with get_db_context() as db:
        await db.execute("DELETE FROM lastfm_daily_plays")
        await db.executemany(
            "INSERT INTO lastfm_daily_plays (date, plays) VALUES (?, ?)",
            [(_day(30), 50), (_day(2), 9), (_day(1), 4)],
        )
        await db.commit()
    # gateway は2日前を返さない（＝その日の scrobble が消えた）
    gateway["days"] = [{"date": _day(1), "plays": 7}, {"date": _day(0), "plays": 3}]

    fetched, stored = await LastfmAdapter().fetch_and_store()

    assert (fetched, stored) == (2, 2)
    assert await _daily() == {_day(30): 50, _day(1): 7, _day(0): 3}
    assert gateway["queries"][0] == {"from": _day(settings.lastfm_daily_lookback_days), "to": _day(0)}


async def test_manual_from_date_reaches_the_gateway(test_db, gateway):
    await LastfmAdapter().fetch_and_store(from_date="2021-01-01")
    assert gateway["queries"][0]["from"] == "2021-01-01"


async def test_refuses_counts_before_the_full_sync_finishes(test_db, gateway):
    async with get_db_context() as db:
        await db.execute("INSERT OR REPLACE INTO lastfm_daily_plays (date, plays) VALUES (?, 5)", (_day(1),))
        await db.commit()
    gateway["fullHistorySynced"] = False
    gateway["days"] = []

    with pytest.raises(RuntimeError, match="full history sync"):
        await LastfmAdapter().fetch_and_store()

    assert (await _daily())[_day(1)] == 5


async def test_reports_the_newest_scrobble_as_last_timestamp(test_db, gateway):
    adapter = LastfmAdapter()
    await adapter.fetch_and_store()
    assert adapter.last_ingested_timestamp == int(datetime(2026, 10, 4, 12, 54, 5, tzinfo=timezone.utc).timestamp())


async def test_daily_minutes_are_plays_times_default_track_length(test_db, gateway):
    gateway["days"] = [{"date": _day(1), "plays": 120}]
    adapter = LastfmAdapter()
    await adapter.fetch_and_store()
    await adapter.aggregate()

    async with get_db_context() as db:
        rows = await db.execute_fetchall(
            "SELECT minutes FROM activity_records WHERE source = 'lastfm' AND date = ?", (_day(1),)
        )
    assert rows[0][0] == round(120 * settings.default_track_duration_seconds / 60, 1)

    activities = await adapter.get_recent_activities(limit=1)
    assert activities[0]["detail"] == "120トラック再生"
