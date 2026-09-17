"""ingest パイプラインが last_timestamp を前へ進めることの回帰テスト。

2026-03-09 から 2026-09-17 までの半年間、パイプラインは ingest_log へ書き戻す値に
`adapter.get_last_timestamp()`（＝1つ前の completed 行の値）を使っていたため、
last_timestamp が一度も進まなかった。lastfm は同じ値を 4,011 回書き続け、毎時
15,000 件超の scrobble を取り直していた（データは INSERT OR IGNORE なので無傷）。
他のソースは last_timestamp が NULL のままで、差分取得そのものが効いていなかった。
"""
from app import database
from app.services import ingest as ingest_service
from app.sources.base import SourceAdapter


class FakeAdapter(SourceAdapter):
    """報告する最新タイムスタンプを差し替えられるアダプタ。"""

    source_id = "fake"
    display_name = "Fake"

    def __init__(self, report_ts: int | None = None):
        self.report_ts = report_ts
        self.seen_from_ts: list[int | None] = []

    async def is_configured(self) -> bool:
        return True

    async def fetch_and_store(self, from_date: str | None = None) -> tuple[int, int]:
        # 差分取得の起点として実際に見える値を記録しておく
        self.seen_from_ts.append(await self.get_last_timestamp())
        if self.report_ts is not None:
            self.last_ingested_timestamp = self.report_ts
        return 1, 1

    async def aggregate(self) -> None:
        return None

    async def get_recent_activities(
        self, limit: int = 8, include_detail: bool = True
    ) -> list[dict]:
        return []


async def _last_log(source_id: str = "fake"):
    async with database.get_db_context() as db:
        rows = await db.execute_fetchall(
            """SELECT status, last_timestamp FROM ingest_log
            WHERE source = ? ORDER BY id DESC LIMIT 1""",
            (source_id,),
        )
    return rows[0]


async def test_reported_timestamp_is_written_back(test_db, monkeypatch):
    adapter = FakeAdapter(report_ts=1_700_000_000)
    monkeypatch.setattr(ingest_service, "get_adapter", lambda _: adapter)

    await ingest_service.run_ingest_pipeline("fake")

    status, last_ts = await _last_log()
    assert status == "completed"
    assert last_ts == 1_700_000_000


async def test_timestamp_advances_on_each_run(test_db, monkeypatch):
    """本体の回帰。以前は2回目も1回目の値のままで、永久に進まなかった。"""
    adapter = FakeAdapter(report_ts=1_700_000_000)
    monkeypatch.setattr(ingest_service, "get_adapter", lambda _: adapter)

    await ingest_service.run_ingest_pipeline("fake")
    adapter.report_ts = 1_700_003_600
    await ingest_service.run_ingest_pipeline("fake")

    _, last_ts = await _last_log()
    assert last_ts == 1_700_003_600
    # 2回目の差分取得は1回目が書いた値を起点にしている
    assert adapter.seen_from_ts == [None, 1_700_000_000]


async def test_previous_value_is_kept_when_adapter_reports_nothing(
    test_db, monkeypatch
):
    """新しいデータが無かった回で last_timestamp を巻き戻さない。"""
    reporting = FakeAdapter(report_ts=1_700_000_000)
    monkeypatch.setattr(ingest_service, "get_adapter", lambda _: reporting)
    await ingest_service.run_ingest_pipeline("fake")

    silent = FakeAdapter(report_ts=None)
    monkeypatch.setattr(ingest_service, "get_adapter", lambda _: silent)
    await ingest_service.run_ingest_pipeline("fake")

    _, last_ts = await _last_log()
    assert last_ts == 1_700_000_000


async def test_stale_report_is_cleared_before_fetch(test_db, monkeypatch):
    """前回の報告値が残っていても、それを書き戻さない。"""
    adapter = FakeAdapter(report_ts=None)
    adapter.last_ingested_timestamp = 1_900_000_000  # 前回の残骸
    monkeypatch.setattr(ingest_service, "get_adapter", lambda _: adapter)

    await ingest_service.run_ingest_pipeline("fake")

    _, last_ts = await _last_log()
    assert last_ts is None


def _track(uts: int) -> dict:
    return {
        "name": "Cherry",
        "artist": {"#text": "スピッツ"},
        "album": {"#text": "空の飛び方"},
        "date": {"uts": str(uts)},
    }


async def test_lastfm_reports_newest_scrobble(test_db, monkeypatch):
    from app.sources import lastfm as lastfm_source

    async def fake_fetch(from_ts=None):
        return [_track(1_700_000_000), _track(1_700_003_600)], 0

    monkeypatch.setattr(lastfm_source, "fetch_all_tracks", fake_fetch)

    adapter = lastfm_source.LastfmAdapter()
    await adapter.fetch_and_store()

    assert adapter.last_ingested_timestamp == 1_700_003_600


async def test_lastfm_holds_timestamp_when_a_page_failed(test_db, monkeypatch):
    """ページを取りこぼした回は進めない。進めるとその scrobble が二度と入らない。"""
    from app.sources import lastfm as lastfm_source

    async def fake_fetch(from_ts=None):
        return [_track(1_700_000_000), _track(1_700_003_600)], 1

    monkeypatch.setattr(lastfm_source, "fetch_all_tracks", fake_fetch)

    adapter = lastfm_source.LastfmAdapter()
    await adapter.fetch_and_store()

    assert adapter.last_ingested_timestamp is None
