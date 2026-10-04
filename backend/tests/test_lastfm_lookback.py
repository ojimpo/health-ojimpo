"""Last.fm の差分取得が、遅れて届いた scrobble を取りこぼさないことの回帰テスト。

Spotify 経由の scrobble は Last.fm に遅れて・順不同で届く。差分取得を
`from=last_timestamp + 1` ちょうどから行っていたため、起点より古い時刻で
後から届いた scrobble を飛び越え、2026-09-18〜10-04 に 12 件を取りこぼした。
"""
from app import database
from app.config import settings
from app.sources import lastfm as lastfm_source
from app.sources.lastfm import LastfmAdapter


def _track(uts: int, name: str) -> dict:
    return {
        "name": name,
        "artist": {"#text": "Artist"},
        "album": {"#text": "Album"},
        "date": {"uts": str(uts)},
    }


class FakeLastfm:
    """Last.fm 側の scrobble 一覧。from_ts 以降だけを返す。"""

    def __init__(self, tracks: list[dict]):
        self.tracks = tracks
        self.seen_from_ts: list[int | None] = []

    async def __call__(self, from_ts: int | None = None):
        self.seen_from_ts.append(from_ts)
        return [t for t in self.tracks if from_ts is None or int(t["date"]["uts"]) >= from_ts], 0


async def _stored_names() -> set[str]:
    async with database.get_db_context() as db:
        rows = await db.execute_fetchall("SELECT track_name FROM lastfm_scrobbles")
    return {r[0] for r in rows}


async def test_late_scrobble_older_than_last_timestamp_is_picked_up(test_db, monkeypatch):
    base = 1_790_000_000
    fake = FakeLastfm([_track(base, "first"), _track(base + 600, "second")])
    monkeypatch.setattr(lastfm_source, "fetch_all_tracks", fake)
    adapter = LastfmAdapter()

    await adapter.fetch_and_store()
    assert adapter.last_ingested_timestamp == base + 600

    # 起点（base + 600）より古い時刻の scrobble が後から届く
    fake.tracks.append(_track(base + 300, "late"))
    monkeypatch.setattr(adapter, "get_last_timestamp", _const(base + 600))
    await adapter.fetch_and_store()

    assert "late" in await _stored_names()
    assert fake.seen_from_ts[-1] == base + 600 + 1 - settings.lastfm_lookback_hours * 3600


async def test_last_timestamp_does_not_move_backwards(test_db, monkeypatch):
    """遡った窓に起点以前の scrobble しか無くても、前回値より戻さない。"""
    base = 1_790_000_000
    fake = FakeLastfm([_track(base, "old")])
    monkeypatch.setattr(lastfm_source, "fetch_all_tracks", fake)
    adapter = LastfmAdapter()
    monkeypatch.setattr(adapter, "get_last_timestamp", _const(base + 3600))

    await adapter.fetch_and_store()

    assert adapter.last_ingested_timestamp == base + 3600


def _const(value):
    async def _f():
        return value
    return _f
