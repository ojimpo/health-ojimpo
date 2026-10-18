"""SyncGatewayAdapter が gateway の「今の状態」に activity_records を合わせることのテスト。

2026-10-19: Filmarks の event_date が公開日で入っていた(1954-04-21 など)。gateway 側で
鑑賞日に直しても、INSERT OR REPLACE は「もう報告されない日」の行を消せず、
health.db に古い日付が残り続けた。守るべき性質:
- 全件取得のとき、gateway が報告しなくなった日の行は消す
- 差分取得(ingest_log に last_timestamp がある)のときは消さない(records が一部のため)
- gateway が0件を返したときは消さない(障害で空が返っただけかもしれない)
- 他ソースの行には触らない
"""
import httpx

from app.config import settings
from app.database import get_db_context
from app.sources import sync_gateway
from app.sources.sync_gateway import SyncGatewayAdapter


def _adapter() -> SyncGatewayAdapter:
    return SyncGatewayAdapter("filmarks", "filmarks", "映画", "movie", "🎬", "#FF9500", "本", "映画を視聴 ")


def _serve(monkeypatch, records: list[dict]) -> list[dict]:
    queries: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        queries.append(dict(request.url.params))
        return httpx.Response(200, json=records)

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        sync_gateway.httpx, "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    monkeypatch.setattr(settings, "sync_gateway_base_url", "http://sync-gateway:8000")
    return queries


async def _seed(rows: list[tuple[str, str]]) -> None:
    async with get_db_context() as db:
        await db.executemany(
            "INSERT INTO activity_records (date, source, category, minutes, raw_value, raw_unit) "
            "VALUES (?, ?, 'movie', 1, 1, '本')",
            rows,
        )
        await db.commit()


async def _dates(source: str = "filmarks") -> list[str]:
    async with get_db_context() as db:
        rows = await db.execute_fetchall(
            "SELECT date FROM activity_records WHERE source = ? ORDER BY date", (source,)
        )
    return [r[0] for r in rows]


def _rec(d: str | None) -> dict:
    return {"event_date": f"{d}T12:00:00" if d else None, "ingested_at": "2026-10-19T00:00:00"}


async def test_removes_days_the_gateway_no_longer_reports(test_db, monkeypatch):
    # 1954-04-21 は公開日で入っていた行。gateway は鑑賞日 2017-04-25 に直した
    await _seed([("1954-04-21", "filmarks"), ("2026-02-13", "filmarks"), ("1954-04-21", "bookmeter")])
    _serve(monkeypatch, [_rec("2017-04-25"), _rec("2026-02-13")])

    await _adapter().fetch_and_store()

    assert await _dates() == ["2017-04-25", "2026-02-13"]
    assert await _dates("bookmeter") == ["1954-04-21"]


async def test_empty_gateway_response_keeps_existing_rows(test_db, monkeypatch):
    await _seed([("2026-02-13", "filmarks")])
    _serve(monkeypatch, [])

    await _adapter().fetch_and_store()

    assert await _dates() == ["2026-02-13"]


async def test_records_without_event_date_do_not_wipe_everything(test_db, monkeypatch):
    await _seed([("2026-02-13", "filmarks")])
    _serve(monkeypatch, [_rec(None)])

    await _adapter().fetch_and_store()

    assert await _dates() == ["2026-02-13"]


async def test_incremental_fetch_does_not_delete(test_db, monkeypatch):
    await _seed([("2026-02-13", "filmarks")])
    async with get_db_context() as db:
        await db.execute(
            "INSERT INTO ingest_log (source, started_at, status, last_timestamp) "
            "VALUES ('filmarks', '2026-10-18 00:00:00', 'completed', 1760000000)"
        )
        await db.commit()
    queries = _serve(monkeypatch, [_rec("2026-10-18")])

    await _adapter().fetch_and_store()

    assert "from" in queries[0]
    assert await _dates() == ["2026-02-13", "2026-10-18"]


async def test_from_date_limits_the_cleanup(test_db, monkeypatch):
    await _seed([("2017-04-25", "filmarks"), ("2026-01-01", "filmarks")])
    _serve(monkeypatch, [_rec("2026-02-13")])

    await _adapter().fetch_and_store(from_date="2026-01-01")

    # from_date より前は触らない
    assert await _dates() == ["2017-04-25", "2026-02-13"]
