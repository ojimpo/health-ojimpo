"""データソース取得健全性の週次レポート。

毎時のingestは「completed / fetched=0」で完走することがあり、トークン失効等の
障害が数週間可視化されない（gcalが2026-05-02〜07-08の2ヶ月間無音停止した実績）。
週次で全アクティブソースの取得状況をまとめ、本人のLINEにのみ送る。

判定ロジック:
- 🔴 broken: OAuthトークンが失効している（実際にrefreshを試みて確認）、
  または直近のingestがfailed
- 🟡 warn: データが一定日数途絶えている
  （baseline系=毎日出るはずのソースは3日、event系=ゼロでも正常なソースは45日）
- 🟢 ok: 上記以外
"""
import logging
from datetime import date

from ..config import settings
from ..database import get_db_context
from .line_notify import send_line_notification
from .oauth import get_valid_token

logger = logging.getLogger(__name__)

# classification=event のソースは「ゼロでも正常」なので長めに取る
STALE_DAYS_DAILY = 3
STALE_DAYS_EVENT = 45

# activity_recordsに別名で記録されるソース（設定ID → レコードのsourceプレフィックス）
RECORD_SOURCE_PREFIXES = {"strava": "strava_"}


async def build_report(today: date | None = None, token_checker=get_valid_token) -> list[dict]:
    """全アクティブソースの健全性を評価したリストを返す（brokenが先頭）。

    token_checkerはテスト用に差し替え可能。既定はOAuthリフレッシュを実際に
    試みるget_valid_token（副作用としてトークンが更新されるが害はない）。
    """
    if today is None:
        today = date.today()

    async with get_db_context() as db:
        sources = await db.execute_fetchall(
            """SELECT id, name, classification FROM source_settings
            WHERE status = 'active' ORDER BY id"""
        )
        last_dates = {
            r[0]: r[1]
            for r in await db.execute_fetchall(
                "SELECT source, MAX(date) FROM activity_records GROUP BY source"
            )
        }
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
    for source_id, name, classification in sources:
        last_date = last_dates.get(source_id)
        if last_date is None:
            prefix = RECORD_SOURCE_PREFIXES.get(source_id, f"{source_id}_")
            candidates = [v for k, v in last_dates.items() if k.startswith(prefix)]
            last_date = max(candidates) if candidates else None
        days_since = (today - date.fromisoformat(last_date)).days if last_date else None

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
