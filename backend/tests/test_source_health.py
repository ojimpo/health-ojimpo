"""Tests for the weekly source health report + migration re-run guard."""
from datetime import date, timedelta

from app import database
from app.services import measurement_state as ms
from app.services.source_health import (
    CLAUDE_CLIENT_VERSION,
    build_report,
    format_report,
    sync_measurement_state,
)

from .conftest import add_record, add_source

TODAY = date(2026, 7, 8)


async def _add_ingest_log(source: str, status: str, error: str | None = None):
    async with database.get_db_context() as db:
        await db.execute(
            """INSERT INTO ingest_log (source, started_at, completed_at, status, error_message)
            VALUES (?, datetime('now'), datetime('now'), ?, ?)""",
            (source, status, error),
        )
        await db.commit()


async def _add_oauth_token(source_id: str):
    async with database.get_db_context() as db:
        await db.execute(
            """INSERT INTO oauth_tokens (source_id, access_token, refresh_token, expires_at)
            VALUES (?, 'at', 'rt', 0)""",
            (source_id,),
        )
        await db.commit()


async def _add_claude_host(
    host: str,
    last: date,
    count: int,
    *,
    step: int = 1,
    version: str | None = CLAUDE_CLIENT_VERSION,
):
    """claude_session_minutes に、last から step日おきに遡って count 件入れる。"""
    async with database.get_db_context() as db:
        for i in range(count):
            await db.execute(
                """INSERT INTO claude_session_minutes (date, host, minutes, client_version)
                VALUES (?, ?, 60, ?)""",
                ((last - timedelta(days=i * step)).isoformat(), host, version),
            )
        await db.commit()


async def _no_token(source_id: str):
    return None


async def _valid_token(source_id: str):
    return "token"


async def test_ok_source(test_db):
    await add_source("lastfm", "music", classification="baseline")
    await add_record(TODAY.isoformat(), "lastfm", "music", 10)
    report = await build_report(today=TODAY, token_checker=_no_token)
    assert report[0]["level"] == "ok"


async def test_stale_baseline_source_warns(test_db):
    await add_source("lastfm", "music", classification="baseline")
    await add_record("2026-07-01", "lastfm", "music", 10)  # 7日前 > 3日
    report = await build_report(today=TODAY, token_checker=_no_token)
    assert report[0]["level"] == "warn"
    assert "7日前" in report[0]["detail"]


async def test_stale_event_source_tolerated(test_db):
    await add_source("steam", "game", classification="event")
    await add_record("2026-07-01", "steam", "game", 1)  # 7日前 <= 45日
    report = await build_report(today=TODAY, token_checker=_no_token)
    assert report[0]["level"] == "ok"


async def test_broken_oauth_token(test_db):
    await add_source("gcal_private", "calendar", classification="event")
    await add_record(TODAY.isoformat(), "gcal_private", "calendar", 1)
    await _add_oauth_token("gcal_private")
    report = await build_report(today=TODAY, token_checker=_no_token)
    assert report[0]["level"] == "broken"
    assert "トークン失効" in report[0]["detail"]
    # 再認証URLがレポート本文に含まれる
    assert "/api/oauth/gcal_private/authorize" in format_report(report, today=TODAY)


async def test_valid_oauth_token_is_ok(test_db):
    await add_source("gcal_private", "calendar", classification="event")
    await add_record(TODAY.isoformat(), "gcal_private", "calendar", 1)
    await _add_oauth_token("gcal_private")
    report = await build_report(today=TODAY, token_checker=_valid_token)
    assert report[0]["level"] == "ok"


async def test_failed_ingest_is_broken(test_db):
    await add_source("steam", "game", classification="event")
    await add_record(TODAY.isoformat(), "steam", "game", 1)
    await _add_ingest_log("steam", "failed", "boom")
    report = await build_report(today=TODAY, token_checker=_no_token)
    assert report[0]["level"] == "broken"
    assert "boom" in report[0]["detail"]


async def test_prefixed_record_sources(test_db):
    """stravaのようにactivity_recordsへ別名（strava_ride等）で入るソース。"""
    await add_source("strava", "exercise", classification="baseline")
    await add_record(TODAY.isoformat(), "strava_ride", "exercise", 30)
    report = await build_report(today=TODAY, token_checker=_no_token)
    assert report[0]["level"] == "ok"


async def test_broken_sorted_first(test_db):
    await add_source("lastfm", "music", classification="baseline")
    await add_record(TODAY.isoformat(), "lastfm", "music", 10)
    await add_source("gcal_private", "calendar", classification="event")
    await _add_oauth_token("gcal_private")
    report = await build_report(today=TODAY, token_checker=_no_token)
    assert [r["id"] for r in report] == ["gcal_private", "lastfm"]


async def test_migrations_do_not_rerun(test_db):
    """再init_dbでUPDATE/DELETE系マイグレーション（027等）が再実行されないこと。

    以前はエラーの出ないマイグレーションが起動のたびに再実行され、
    claude/githubのactivity_recordsが毎回消えていた。
    """
    await add_record(TODAY.isoformat(), "claude", "coding", 100)
    await database.init_db()
    async with database.get_db_context() as db:
        rows = await db.execute_fetchall(
            "SELECT COUNT(*) FROM activity_records WHERE source = 'claude'"
        )
    assert rows[0][0] == 1


# --- 取得量の急減（2026-08のlastfm事故: データは来ているのに量が崩壊していた） ---

VOL_TODAY = date(2026, 8, 16)


async def _fill_daily(source: str, category: str, start: date, days: int, value: float):
    for i in range(days):
        await add_record((start + timedelta(days=i)).isoformat(), source, category, value)


async def test_volume_collapse_warns_while_data_still_trickles(test_db):
    """最終データが1日前でも、量が平常時から崩壊していれば警告する。

    これが今回の再発防止の本体。存在チェックだけだと数日おきに1件でも入れば
    「最終データ1日前」でokになり、8週間気付けなかった。
    """
    await add_source("lastfm", "music", classification="baseline", base_value=1200)
    # 98日前〜15日前は平常運転（毎日170分＝基準1200分/週相当）
    await _fill_daily("lastfm", "music", VOL_TODAY - timedelta(days=97), 83, 170)
    # 直近14日は数日おきに数分だけ（スクロブラー停止後の実際の形）
    for offset in (12, 8, 2):
        await add_record((VOL_TODAY - timedelta(days=offset)).isoformat(), "lastfm", "music", 5)

    report = await build_report(today=VOL_TODAY, token_checker=_no_token)
    assert report[0]["level"] == "warn"
    assert "取得量が急減" in report[0]["detail"]
    assert report[0]["days_since"] == 2  # 途絶チェックだけならokだった


async def test_steady_source_is_ok(test_db):
    await add_source("lastfm", "music", classification="baseline", base_value=1200)
    await _fill_daily("lastfm", "music", VOL_TODAY - timedelta(days=97), 98, 170)
    report = await build_report(today=VOL_TODAY, token_checker=_no_token)
    assert report[0]["level"] == "ok"


async def test_mild_dip_is_not_flagged(test_db):
    """平常時の半分程度に落ちた程度では鳴らさない（閾値30%）。"""
    await add_source("lastfm", "music", classification="baseline", base_value=1200)
    await _fill_daily("lastfm", "music", VOL_TODAY - timedelta(days=97), 84, 170)
    await _fill_daily("lastfm", "music", VOL_TODAY - timedelta(days=13), 14, 85)
    report = await build_report(today=VOL_TODAY, token_checker=_no_token)
    assert report[0]["level"] == "ok"


async def test_event_source_volume_not_checked(test_db):
    """event系はゼロでも正常なので取得量では判定しない。"""
    await add_source("filmarks", "movie", classification="event", base_value=6,
                     aggregation_period=90)
    await _fill_daily("filmarks", "movie", VOL_TODAY - timedelta(days=97), 84, 2)
    await add_record((VOL_TODAY - timedelta(days=1)).isoformat(), "filmarks", "movie", 1)
    report = await build_report(today=VOL_TODAY, token_checker=_no_token)
    assert report[0]["level"] == "ok"


async def test_daily_avg_source_volume_not_checked(test_db):
    """状態系(daily_avg)はraw_valueが『量』でないので対象外。

    ouraはstress(900〜2700)がsleep/readiness(0〜100)を飲み込むため、合計の増減を
    取得障害とみなすと誤検知する。欠測は日数ベースの途絶チェックで拾う。
    """
    await add_source("oura", "sleep", classification="baseline", base_value=80,
                     score_method="daily_avg")
    await _fill_daily("oura", "sleep", VOL_TODAY - timedelta(days=97), 84, 2000)
    await _fill_daily("oura", "sleep", VOL_TODAY - timedelta(days=13), 14, 100)
    report = await build_report(today=VOL_TODAY, token_checker=_no_token)
    assert report[0]["level"] == "ok"


async def test_new_source_without_history_not_flagged(test_db):
    """履歴が揃っていない新規ソースは比較対象がないので判定しない。"""
    await add_source("newsrc", "music", classification="baseline", base_value=1200)
    await _fill_daily("newsrc", "music", VOL_TODAY - timedelta(days=20), 7, 170)
    await add_record((VOL_TODAY - timedelta(days=1)).isoformat(), "newsrc", "music", 5)
    report = await build_report(today=VOL_TODAY, token_checker=_no_token)
    assert report[0]["level"] == "ok"


async def test_claude_host_silence_warns(test_db):
    """毎日送ってくる端末が7日以上黙ったら警告する。

    2026-05-26〜08-16 に arigato-nas のフックが死んでいたのに、他端末が送っていたため
    ソース単位では ok に見えて3ヶ月気付けなかった事故の再発防止。
    """
    await add_source("claude", "coding", classification="event")
    await add_record(VOL_TODAY.isoformat(), "claude", "coding", 100)  # 他端末が送っている
    await _add_claude_host("nas", VOL_TODAY - timedelta(days=90), 60, step=1)
    await _add_claude_host("laptop", VOL_TODAY, 6, step=2)

    report = await build_report(today=VOL_TODAY, token_checker=_no_token)
    levels = {r["id"]: r["level"] for r in report}
    assert levels["claude"] == "ok"  # ソース単位では生きて見える
    assert levels["claude:nas"] == "warn"
    assert "claude:laptop" not in levels
    detail = next(r["detail"] for r in report if r["id"] == "claude:nas")
    assert "送信なし" in detail


async def test_claude_host_sporadic_not_flagged(test_db):
    """たまにしか触らない端末は、その端末の平常間隔で測る（毎日基準で鳴らさない）。"""
    await add_source("claude", "coding", classification="event")
    await add_record(VOL_TODAY.isoformat(), "claude", "coding", 100)
    # 20日おきに使う端末が10日沈黙している状態
    await _add_claude_host("desktop", VOL_TODAY - timedelta(days=10), 6, step=20)

    report = await build_report(today=VOL_TODAY, token_checker=_no_token)
    assert not [r for r in report if r["id"].startswith("claude:")]


async def test_claude_host_retired_not_flagged(test_db):
    """長く使っていない端末は引退扱いで鳴らし続けない。"""
    await add_source("claude", "coding", classification="event")
    await add_record(VOL_TODAY.isoformat(), "claude", "coding", 100)
    await _add_claude_host("oldtab", VOL_TODAY - timedelta(days=150), 6, step=1)

    report = await build_report(today=VOL_TODAY, token_checker=_no_token)
    assert not [r for r in report if r["id"].startswith("claude:")]


async def test_claude_host_new_not_flagged(test_db):
    """履歴が数件しかない端末は平常間隔を測れないので判定しない。"""
    await add_source("claude", "coding", classification="event")
    await add_record(VOL_TODAY.isoformat(), "claude", "coding", 100)
    await _add_claude_host("fresh", VOL_TODAY - timedelta(days=30), 3, step=1)

    report = await build_report(today=VOL_TODAY, token_checker=_no_token)
    assert not [r for r in report if r["id"].startswith("claude:")]


async def test_claude_host_stale_version_warns(test_db):
    """現役端末が古いレポータを動かしていたら指摘する（version未申告=v1）。"""
    await add_source("claude", "coding", classification="event")
    await add_record(VOL_TODAY.isoformat(), "claude", "coding", 100)
    await _add_claude_host("laptop", VOL_TODAY, 6, step=1, version=None)

    report = await build_report(today=VOL_TODAY, token_checker=_no_token)
    row = next(r for r in report if r["id"] == "claude:laptop")
    assert row["level"] == "warn"
    assert "レポータ v1" in row["detail"]


async def test_claude_host_current_version_is_quiet(test_db):
    await add_source("claude", "coding", classification="event")
    await add_record(VOL_TODAY.isoformat(), "claude", "coding", 100)
    await _add_claude_host("laptop", VOL_TODAY, 6, step=1, version=CLAUDE_CLIENT_VERSION)

    report = await build_report(today=VOL_TODAY, token_checker=_no_token)
    assert not [r for r in report if r["id"].startswith("claude:")]


async def test_always_quiet_source_not_flagged(test_db):
    """元々基準値に遠く届かないソースは毎週鳴らしても意味がないので判定しない。"""
    await add_source("quiet", "music", classification="baseline", base_value=1200)
    await _fill_daily("quiet", "music", VOL_TODAY - timedelta(days=97), 84, 3)
    await add_record((VOL_TODAY - timedelta(days=1)).isoformat(), "quiet", "music", 1)
    report = await build_report(today=VOL_TODAY, token_checker=_no_token)
    assert report[0]["level"] == "ok"


# --- 計測状態への反映（source_measurement_state との接続） ---


async def test_token_failure_marks_broken(test_db):
    await add_source("gcal_private", "calendar", classification="event")
    await add_record(TODAY.isoformat(), "gcal_private", "calendar", 1)
    await _add_oauth_token("gcal_private")
    report = await build_report(today=TODAY, token_checker=_no_token)

    assert (await sync_measurement_state(report))["marked"] == ["gcal_private"]
    assert (await ms.get_broken_sources())["gcal_private"]["reason"] == ms.REASON_TOKEN


async def test_failed_ingest_marks_broken(test_db):
    await add_source("steam", "game", classification="event")
    await add_record(TODAY.isoformat(), "steam", "game", 1)
    await _add_ingest_log("steam", "failed", "boom")
    report = await build_report(today=TODAY, token_checker=_no_token)

    await sync_measurement_state(report)
    assert (await ms.get_broken_sources())["steam"]["reason"] == ms.REASON_INGEST_FAILED


async def test_volume_collapse_alone_never_marks_broken(test_db):
    """取得量の急減は本物の低下と区別がつかないので、証拠として使わない。

    ここが破れると、活動が減っただけのカテゴリが軸から消える。
    """
    await add_source("lastfm", "music", classification="baseline", base_value=1200)
    await _fill_daily("lastfm", "music", VOL_TODAY - timedelta(days=97), 83, 170)
    for offset in (12, 8, 2):
        await add_record((VOL_TODAY - timedelta(days=offset)).isoformat(), "lastfm", "music", 5)

    report = await build_report(today=VOL_TODAY, token_checker=_no_token)
    assert report[0]["volume_collapse"] is True      # 検知はする
    assert report[0]["reason"] is None               # が、証拠にはしない
    await sync_measurement_state(report)
    assert await ms.get_broken_sources() == {}       # 軸からは外れない


async def test_auto_reason_recovers_when_failure_clears(test_db):
    await add_source("gcal_private", "calendar", classification="event")
    await add_record(TODAY.isoformat(), "gcal_private", "calendar", 1)
    await ms.mark_broken("gcal_private", ms.REASON_TOKEN)

    report = await build_report(today=TODAY, token_checker=_valid_token)
    assert (await sync_measurement_state(report))["recovered"] == ["gcal_private"]
    assert await ms.get_broken_sources() == {}


async def test_user_reported_needs_full_recovery(test_db):
    """本人が『壊れている』と言った状態は、取得量まで戻って初めて解除する。"""
    await add_source("lastfm", "music", classification="baseline", base_value=1200)
    await _fill_daily("lastfm", "music", VOL_TODAY - timedelta(days=97), 83, 170)
    for offset in (12, 8, 2):
        await add_record((VOL_TODAY - timedelta(days=offset)).isoformat(), "lastfm", "music", 5)
    await ms.mark_broken("lastfm", ms.REASON_USER_REPORTED)

    # まだ取得量が戻っていない（level='warn'）→ 解除しない
    report = await build_report(today=VOL_TODAY, token_checker=_no_token)
    await sync_measurement_state(report)
    assert "lastfm" in await ms.get_broken_sources()

    # 平常量に戻る（level='ok'）→ 自動で解除。
    # 既存レコードと衝突しないよう、以降の日付を埋めて基準日を進める。
    later = VOL_TODAY + timedelta(days=20)
    await _fill_daily("lastfm", "music", VOL_TODAY + timedelta(days=1), 20, 170)
    report = await build_report(today=later, token_checker=_no_token)
    assert report[0]["level"] == "ok"
    assert (await sync_measurement_state(report))["recovered"] == ["lastfm"]


async def test_report_lists_excluded_sources(test_db):
    """除外中のソースを黙って消さず、レポートに必ず出す。"""
    await add_source("lastfm", "music", classification="baseline")
    await add_record(TODAY.isoformat(), "lastfm", "music", 10)
    await ms.mark_broken("lastfm", ms.REASON_USER_REPORTED)

    report = await build_report(today=TODAY, token_checker=_no_token)
    text = format_report(report, today=TODAY, broken=await ms.get_broken_sources())
    assert "スコアから除外中（1件）" in text
    assert "本人申告" in text
