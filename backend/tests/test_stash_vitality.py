"""Stash vitality: 累積 play_duration を「観た日」へ配分するロジックのテスト。"""

from app.sources.stash_vitality import StashVitalityAdapter

attribute = StashVitalityAdapter._attribute_seconds


def scene(scene_id, duration, history, last_played_at=None):
    return {
        "id": scene_id,
        "play_duration": duration,
        "play_history": history,
        "last_played_at": last_played_at,
    }


def test_first_sync_spreads_cumulative_duration_over_history():
    """スナップショットが無い初回は差分が取れないので全履歴に等分する。"""
    scenes = [scene("1", 600, ["2026-08-02T10:00:00Z", "2026-08-01T10:00:00Z"])]

    assert attribute(scenes, {}) == {"2026-08-01": 300.0, "2026-08-02": 300.0}


def test_incremental_attributes_only_the_delta_to_new_plays():
    """2回目以降は増えた秒数だけを、新しく増えた再生の日に配分する。"""
    scenes = [
        scene(
            "1",
            900,
            ["2026-08-03T09:00:00Z", "2026-08-02T10:00:00Z", "2026-08-01T10:00:00Z"],
        )
    ]
    prev = {"1": (600.0, "2026-08-02T10:00:00Z")}

    # 過去日は据え置き、増えた 300 秒だけが 8/3 に載る
    assert attribute(scenes, prev) == {"2026-08-03": 300.0}


def test_resume_without_new_play_event_lands_on_last_played_day():
    """再生イベントは増えず再生時間だけ伸びた場合は最終再生日に加算する。"""
    scenes = [
        scene("1", 800, ["2026-08-01T10:00:00Z"], last_played_at="2026-08-01T10:00:00Z")
    ]
    prev = {"1": (600.0, "2026-08-01T10:00:00Z")}

    assert attribute(scenes, prev) == {"2026-08-01": 200.0}


def test_no_change_attributes_nothing():
    """同じ ingest を2回流しても二重計上しない（冪等）。"""
    scenes = [scene("1", 600, ["2026-08-01T10:00:00Z"])]
    prev = {"1": (600.0, "2026-08-01T10:00:00Z")}

    assert attribute(scenes, prev) == {}


def test_shrinking_duration_is_ignored():
    """履歴削除や再スキャンで累積値が減っても負の秒数を撒かない。"""
    scenes = [scene("1", 100, ["2026-08-01T10:00:00Z"])]
    prev = {"1": (600.0, "2026-08-01T10:00:00Z")}

    assert attribute(scenes, prev) == {}


def test_history_order_does_not_matter():
    """Stash の play_history は降順で返るが、配分は昇順ソートに依存しない。"""
    desc = [scene("1", 900, ["2026-08-03T09:00:00Z", "2026-08-01T10:00:00Z"])]
    asc = [scene("1", 900, ["2026-08-01T10:00:00Z", "2026-08-03T09:00:00Z"])]

    assert attribute(desc, {}) == attribute(asc, {})


def test_multiple_scenes_accumulate_on_the_same_day():
    scenes = [
        scene("1", 600, ["2026-08-01T10:00:00Z"]),
        scene("2", 300, ["2026-08-01T21:00:00Z"]),
    ]

    assert attribute(scenes, {}) == {"2026-08-01": 900.0}


def test_new_scene_alongside_known_scenes():
    """既知シーンは差分、未知シーンは全履歴按分と、混在しても取り違えない。"""
    scenes = [
        scene("1", 900, ["2026-08-03T09:00:00Z", "2026-08-01T10:00:00Z"]),
        scene("2", 120, ["2026-08-03T20:00:00Z"]),
    ]
    prev = {"1": (600.0, "2026-08-01T10:00:00Z")}

    assert attribute(scenes, prev) == {"2026-08-03": 420.0}
