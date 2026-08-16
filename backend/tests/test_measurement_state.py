"""計測状態（壊れているソースの記録と、軸集計への反映）のテスト。

設計上いちばん大事なのは「値が低いこと」で除外しないこと。除外には
トークン失効・ingest失敗・本人申告という積極的な証拠が要る。ここでは
証拠があるときだけ外れること、外した結果スコアが良く見えないことを見る。
"""
from app.services import measurement_state as ms

from .conftest import add_source


# --- 状態の読み書き ---


async def test_mark_broken_and_recover(test_db):
    await add_source("lastfm", "music")
    assert await ms.mark_broken("lastfm", ms.REASON_USER_REPORTED, "本人申告") is True
    broken = await ms.get_broken_sources()
    assert broken["lastfm"]["reason"] == ms.REASON_USER_REPORTED
    assert broken["lastfm"]["detected_at"]

    assert await ms.mark_ok("lastfm") is True          # broken からの復帰
    assert await ms.get_broken_sources() == {}
    assert await ms.mark_ok("lastfm") is False         # 既に ok なら復帰ではない


async def test_mark_broken_is_idempotent_per_reason(test_db):
    """同じ理由の再通知で通知が連投されないよう、2回目は False を返す。"""
    await add_source("gcal_private", "calendar")
    assert await ms.mark_broken("gcal_private", ms.REASON_TOKEN) is True
    assert await ms.mark_broken("gcal_private", ms.REASON_TOKEN) is False
    # 理由が変わったら「新しい事象」として扱う
    assert await ms.mark_broken("gcal_private", ms.REASON_INGEST_FAILED) is True


async def test_detected_at_survives_reason_change(test_db):
    """いつから壊れているかは、理由が変わっても最初の検知時刻を保つ。"""
    await add_source("gcal_private", "calendar")
    await ms.mark_broken("gcal_private", ms.REASON_TOKEN)
    first = (await ms.get_broken_sources())["gcal_private"]["detected_at"]
    await ms.mark_broken("gcal_private", ms.REASON_INGEST_FAILED)
    assert (await ms.get_broken_sources())["gcal_private"]["detected_at"] == first


async def test_asked_at_roundtrip(test_db):
    await add_source("lastfm", "music")
    assert await ms.get_asked_at("lastfm") is None
    await ms.record_asked("lastfm")
    assert await ms.get_asked_at("lastfm") is not None


async def test_record_asked_does_not_break_source(test_db):
    """質問しただけでは壊れている扱いにしない（答えを聞くまでは判断しない）。"""
    await add_source("lastfm", "music")
    await ms.record_asked("lastfm")
    assert await ms.get_broken_sources() == {}


# --- 軸集計への反映 ---


class TestCategoryScores:
    def test_low_score_alone_is_never_excluded(self):
        """いちばん重要な性質: 値が低いだけのカテゴリは絶対に外さない。

        ここを外すと本物の活動低下が消え、健康軸の存在意義が無くなる。
        """
        scores, unknown = ms.category_scores({"music": [("lastfm", 0.0)]}, broken={})
        assert scores == {"music": 0.0}
        assert unknown == []

    def test_broken_source_excluded(self):
        scores, unknown = ms.category_scores(
            {"music": [("lastfm", 8.0)]}, broken={"lastfm": {"reason": "user_reported"}}
        )
        assert scores == {}
        assert unknown == ["music"]

    def test_surviving_source_keeps_category_alive(self):
        """複数ソースのカテゴリは、片方が壊れても生きている側で計測を続ける。"""
        scores, unknown = ms.category_scores(
            {"exercise": [("strava", 40.0), ("oura_steps", 100.0)]},
            broken={"strava": {"reason": "token"}},
        )
        assert scores == {"exercise": 100.0}   # 壊れたstravaは平均に混ぜない
        assert unknown == []

    def test_averages_all_alive_sources(self):
        scores, _ = ms.category_scores(
            {"vitality": [("nextdns_vitality", 60.0), ("stash_vitality", 80.0)]}, broken={}
        )
        assert scores == {"vitality": 70.0}

    def test_unknown_sorted(self):
        scores, unknown = ms.category_scores(
            {"music": [("lastfm", 1.0)], "cd": [("kashidashi_cd", 1.0)]},
            broken={"lastfm": {}, "kashidashi_cd": {}},
        )
        assert scores == {}
        assert unknown == ["cd", "music"]


class TestAxisMeasurable:
    def test_enough_categories(self):
        assert ms.axis_is_measurable(ms.MIN_MEASURABLE_CATEGORIES) is True
        assert ms.axis_is_measurable(ms.MIN_MEASURABLE_CATEGORIES + 3) is True

    def test_too_few_is_not_measurable(self):
        """壊れたソースを外し続けた末に「1カテゴリだけ生きていて満点」を防ぐ安全弁。

        計測不能が増えたときスコアが良くなってはいけない。
        """
        assert ms.axis_is_measurable(ms.MIN_MEASURABLE_CATEGORIES - 1) is False
        assert ms.axis_is_measurable(0) is False
