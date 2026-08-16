"""データソース取得健全性の週次レポート。

毎時のingestは「completed / fetched=0」で完走することがあり、トークン失効等の
障害が数週間可視化されない（gcalが2026-05-02〜07-08の2ヶ月間無音停止した実績）。
週次で全アクティブソースの取得状況をまとめ、本人のLINEにのみ送る。

判定ロジック:
- 🔴 broken: OAuthトークンが失効している（実際にrefreshを試みて確認）、
  または直近のingestがfailed
- 🟡 warn: データが一定日数途絶えている
  （baseline系=毎日出るはずのソースは3日、event系=ゼロでも正常なソースは45日）
- 🟡 warn: データは来ているが**取得量が平常時から急減**している（_volume_collapse）
- 🟢 ok: 上記以外

取得量チェックを足した理由（2026-08-16）: lastfm は 7/24 に Spotify 連携が失効して
scrobble が 100〜140件/日 → 週1〜10件に崩壊したが、Pano Scrobbler と Plex が数日おきに
数件だけ送り続けたため「最終データ0〜2日前」となり、**8週間一度も警告が出なかった**。
存在チェックだけでは量の崩壊は原理的に見えない。
"""
import logging
import statistics
from datetime import date, timedelta

from ..config import settings
from ..database import get_db_context
from ..sources import strava as strava_source
from .line_notify import send_line_notification
from .oauth import get_valid_token

logger = logging.getLogger(__name__)

# classification=event のソースは「ゼロでも正常」なので長めに取る
STALE_DAYS_DAILY = 3
STALE_DAYS_EVENT = 45

# activity_recordsに別名で記録されるソース（設定ID → レコードのsourceプレフィックス）
RECORD_SOURCE_PREFIXES = {"strava": "strava_"}

# --- 取得量の急減判定 ---
# 直近14日の合計を、その前の6窓（=84日）の中央値と比べる。中央値を使うのは
# 旅行や繁忙で1窓だけ落ちても引きずられないため。
VOLUME_WINDOW_DAYS = 14
VOLUME_HISTORY_WINDOWS = 6
# 平常時の30%未満まで落ちたら異常とみなす。実データ16週で振った結果:
#   25% → lastfm事故を8/9に検知、誤検知0
#   30% → lastfm事故を8/2（障害開始の9日後）に検知、誤検知0  ← これを採用
#   35% → 誤検知1（5/24 strava、単に運動が軽い2週間だった）
# 窓を7日に縮めても検知日は8/2で変わらず、stash_vitalityの誤検知が増えるだけだった。
VOLUME_DROP_RATIO = 0.30
# 平常時の中央値が「基準値から期待される量」の半分にも届かないソースは判定しない。
# 元々ほとんどデータが出ていないソースに対して毎週警告を出しても意味がないため。
VOLUME_MIN_BASELINE_RATIO = 0.5


def _matching_record_keys(source_id: str, keys) -> list[str]:
    """設定IDに対応する activity_records.source のキー一覧。

    通常は同名。stravaのように別名（strava_ride等）で入るソースはプレフィックス一致。
    """
    if source_id in keys:
        return [source_id]
    prefix = RECORD_SOURCE_PREFIXES.get(source_id, f"{source_id}_")
    return [k for k in keys if k.startswith(prefix)]


def _volume_checkable(classification: str, score_method: str) -> bool:
    """取得量の急減判定を当てにいくソースか。

    - event系は「ゼロでも正常」なので対象外。
    - score_method='daily_avg'（oura等の状態系）も対象外。これらのraw_valueは
      「量」ではなく「水準」で、しかもカテゴリ間でスケールが違う（ouraはstressの
      900〜2700がsleep/readinessの0〜100を飲み込む）。合計の増減は取得障害では
      なく実際の状態変動なので、量として比べると誤検知になる。欠測は日数ベースの
      途絶チェックで拾える。
    """
    return classification != "event" and score_method != "daily_avg"


def _window_sums(daily: dict[str, float], today: date) -> list[float]:
    """todayを末尾とする14日窓の合計を、直近から過去へ 1+VOLUME_HISTORY_WINDOWS 個返す。"""
    sums = []
    for w in range(VOLUME_HISTORY_WINDOWS + 1):
        end = today - timedelta(days=w * VOLUME_WINDOW_DAYS)
        sums.append(
            sum(
                daily.get((end - timedelta(days=i)).isoformat(), 0.0)
                for i in range(VOLUME_WINDOW_DAYS)
            )
        )
    return sums


def _volume_collapse(
    daily: dict[str, float],
    today: date,
    first_date: str | None,
    base_value: float,
    period: int,
) -> tuple[float, float] | None:
    """取得量の急減を検出し (直近窓の合計, 平常時の中央値) を返す。正常ならNone。

    比較対象の履歴が丸ごと揃っていないソース（新規追加直後など）は判定しない。
    """
    history_days = VOLUME_WINDOW_DAYS * (VOLUME_HISTORY_WINDOWS + 1)
    if not first_date or date.fromisoformat(first_date) > today - timedelta(days=history_days - 1):
        return None

    windows = _window_sums(daily, today)
    recent, median = windows[0], statistics.median(windows[1:])

    expected = base_value * VOLUME_WINDOW_DAYS / period if period else 0.0
    if median <= 0 or median < expected * VOLUME_MIN_BASELINE_RATIO:
        return None
    if recent < median * VOLUME_DROP_RATIO:
        return recent, median
    return None


async def _check_token(source_id: str):
    """トークンの生存確認。

    strava だけは別扱い: このアプリは strava-autopilot と同じ Strava client を
    共有しており、両者が独立にリフレッシュすると **リフレッシュトークンの
    ローテーションで片方が無効化されうる**。ヘルスチェックは get_valid_token を
    副作用込み（＝期限切れならリフレッシュ）で呼ぶので、ここで踏むと壊す。
    ゲートウェイ設定時はゲートウェイに聞く（更新はあちら側で一元管理）。
    """
    if source_id == "strava" and strava_source._gateway_configured():
        return await strava_source._get_access_token()
    return await get_valid_token(source_id)


async def build_report(today: date | None = None, token_checker=_check_token) -> list[dict]:
    """全アクティブソースの健全性を評価したリストを返す（brokenが先頭）。

    token_checkerはテスト用に差し替え可能。既定は_check_token（OAuthリフレッシュを
    実際に試みる。ただしstravaはゲートウェイに委譲する。上の_check_token参照）。
    """
    if today is None:
        today = date.today()

    async with get_db_context() as db:
        sources = await db.execute_fetchall(
            """SELECT id, name, classification, base_value, aggregation_period, score_method
            FROM source_settings WHERE status = 'active' ORDER BY id"""
        )
        last_dates = {
            r[0]: r[1]
            for r in await db.execute_fetchall(
                "SELECT source, MAX(date) FROM activity_records GROUP BY source"
            )
        }
        first_dates = {
            r[0]: r[1]
            for r in await db.execute_fetchall(
                "SELECT source, MIN(date) FROM activity_records GROUP BY source"
            )
        }
        volume_from = (
            today - timedelta(days=VOLUME_WINDOW_DAYS * (VOLUME_HISTORY_WINDOWS + 1) - 1)
        ).isoformat()
        daily_by_source: dict[str, dict[str, float]] = {}
        for src, d, total in await db.execute_fetchall(
            """SELECT source, date, SUM(raw_value) FROM activity_records
            WHERE date >= ? GROUP BY source, date""",
            (volume_from,),
        ):
            daily_by_source.setdefault(src, {})[d] = float(total or 0)
        last_ingests = {
            r[0]: (r[1], r[2])
            for r in await db.execute_fetchall(
                """SELECT source, status, error_message FROM ingest_log
                WHERE id IN (SELECT MAX(id) FROM ingest_log GROUP BY source)"""
            )
        }
        oauth_source_ids = {
            r[0] for r in await db.execute_fetchall("SELECT source_id FROM oauth_tokens")
        }

    report = []
    for source_id, name, classification, base_value, period, score_method in sources:
        record_keys = _matching_record_keys(source_id, last_dates.keys())
        ends = [last_dates[k] for k in record_keys if last_dates.get(k)]
        last_date = max(ends) if ends else None
        starts = [first_dates[k] for k in record_keys if first_dates.get(k)]
        first_date = min(starts) if starts else None
        days_since = (today - date.fromisoformat(last_date)).days if last_date else None

        daily: dict[str, float] = {}
        for k in record_keys:
            for d, v in daily_by_source.get(k, {}).items():
                daily[d] = daily.get(d, 0.0) + v

        ingest_status, ingest_error = last_ingests.get(source_id, (None, None))

        token_ok = None
        if source_id in oauth_source_ids:
            token_ok = await token_checker(source_id) is not None

        stale_limit = STALE_DAYS_EVENT if classification == "event" else STALE_DAYS_DAILY
        if token_ok is False:
            level, detail = "broken", "OAuthトークン失効 — 要再認証"
        elif ingest_status == "failed":
            level = "broken"
            detail = f"直近ingest失敗: {(ingest_error or '')[:60]}"
        elif days_since is None:
            level, detail = "warn", "データなし"
        elif days_since > stale_limit:
            level, detail = "warn", f"最終データ {last_date}（{days_since}日前）"
        elif _volume_checkable(classification, score_method) and (
            collapse := _volume_collapse(
                daily, today, first_date, float(base_value), int(period)
            )
        ):
            recent, median = collapse
            level = "warn"
            detail = (
                f"取得量が急減（直近{VOLUME_WINDOW_DAYS}日 {recent:,.0f} / "
                f"平常時 {median:,.0f} = {recent / median * 100:.0f}%）"
            )
        else:
            level, detail = "ok", f"最終データ {last_date}"

        report.append({
            "id": source_id,
            "name": name,
            "level": level,
            "detail": detail,
            "last_date": last_date,
            "days_since": days_since,
            "oauth": token_ok is not None,
        })

    order = {"broken": 0, "warn": 1, "ok": 2}
    report.sort(key=lambda r: (order[r["level"]], r["id"]))
    return report


def format_report(report: list[dict], today: date | None = None) -> str:
    if today is None:
        today = date.today()
    counts = {"broken": 0, "warn": 0, "ok": 0}
    for r in report:
        counts[r["level"]] += 1

    lines = [
        f"🩺 ソース週次ヘルスチェック {today.month}/{today.day}",
        f"🔴 {counts['broken']} / 🟡 {counts['warn']} / 🟢 {counts['ok']}",
    ]
    for r in report:
        if r["level"] == "ok":
            continue
        mark = "🔴" if r["level"] == "broken" else "🟡"
        lines.append(f"\n{mark} {r['name']}")
        lines.append(f"　{r['detail']}")
        if r["level"] == "broken" and r["oauth"]:
            lines.append(f"　https://{settings.app_domain}/api/oauth/{r['id']}/authorize")

    if counts["broken"] == 0 and counts["warn"] == 0:
        lines.append("\n全ソース正常です ✨")
    return "\n".join(lines)


async def send_weekly_report() -> bool:
    """週次レポートを本人のLINEに送る。宛先はLINE_OWNER_USER_IDのみ。"""
    if not settings.line_owner_user_id:
        logger.info("Source health report: LINE_OWNER_USER_ID not configured, skipping")
        return False
    report = await build_report()
    await send_line_notification(settings.line_owner_user_id, format_report(report))
    logger.info("Source health report sent (%d sources)", len(report))
    return True
