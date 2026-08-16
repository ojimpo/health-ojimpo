"""ソースの「計測が壊れているか」の状態管理。

スコアは「やっていない」と「計測が壊れている」を区別できていなかった
（2026-07 の Last.fm、migration 047 のコメント参照）。ここはその区別を
明示的に持ち、壊れているソースを軸集計から外すための土台。

**除外は「値が低いこと」を条件にしない。** 値の低さで外すと本物の活動低下まで
消えてしまい、健康軸の存在意義が無くなる。除外には必ず計測が壊れている
積極的な証拠（トークン失効・ingest失敗・本人の申告）を要求する。
取得量の急減それ自体は証拠にしない — 本物の低下と区別がつかないので、
services/source_health.py が検知したら本人に聞く（reason='user_reported'）。

UNKNOWN が増えたときスコアが「良く」なってはいけないので、計測できている
カテゴリが MIN_MEASURABLE_CATEGORIES を割ったら軸自体を UNKNOWN にする。
"""
import logging

from ..database import get_db_context

logger = logging.getLogger(__name__)

# 壊れている証拠の種類。取得量の急減はここに入れない（本物の低下と区別不能）。
REASON_TOKEN = "token"
REASON_INGEST_FAILED = "ingest_failed"
REASON_USER_REPORTED = "user_reported"

REASON_LABELS = {
    REASON_TOKEN: "OAuthトークン失効",
    REASON_INGEST_FAILED: "ingest失敗",
    REASON_USER_REPORTED: "本人申告（記録が壊れている）",
}

# 軸を名乗るのに最低限必要な「計測できているカテゴリ数」。
# これを割ったら軸スコアは出さない。壊れたソースを外し続けた挙句
# 「1カテゴリだけ生きていて満点」になるのを防ぐための安全弁。
MIN_MEASURABLE_CATEGORIES = 3


async def get_broken_sources() -> dict[str, dict]:
    """state='broken' のソースを {source_id: {reason, detail, detected_at}} で返す。"""
    async with get_db_context() as db:
        rows = await db.execute_fetchall(
            """SELECT source_id, reason, detail, detected_at
            FROM source_measurement_state WHERE state = 'broken'"""
        )
    return {
        r[0]: {"reason": r[1], "detail": r[2], "detected_at": r[3]}
        for r in rows
    }


async def mark_broken(source_id: str, reason: str, detail: str | None = None) -> bool:
    """ソースを broken にする。既に同じ理由で broken なら何もしない。

    戻り値は「今回新しく broken になったか」。通知の連投を避けるのに使う。
    """
    async with get_db_context() as db:
        rows = await db.execute_fetchall(
            "SELECT state, reason FROM source_measurement_state WHERE source_id = ?",
            (source_id,),
        )
        if rows and rows[0][0] == "broken" and rows[0][1] == reason:
            return False
        await db.execute(
            """INSERT INTO source_measurement_state
                (source_id, state, reason, detail, detected_at, updated_at)
            VALUES (?, 'broken', ?, ?, datetime('now'), datetime('now'))
            ON CONFLICT(source_id) DO UPDATE SET
                state = 'broken', reason = excluded.reason, detail = excluded.detail,
                detected_at = COALESCE(source_measurement_state.detected_at, datetime('now')),
                updated_at = datetime('now')""",
            (source_id, reason, detail),
        )
        await db.commit()
    logger.info("Measurement state: %s -> broken (%s)", source_id, reason)
    return True


async def mark_ok(source_id: str) -> bool:
    """ソースを ok に戻す。戻り値は「実際に broken から復帰したか」。

    本人が申告した場合も含めて自動で戻す。解除操作を要求すると、申告しっぱなしで
    永久に軸から外れ続けることになる。
    """
    async with get_db_context() as db:
        rows = await db.execute_fetchall(
            "SELECT state FROM source_measurement_state WHERE source_id = ?",
            (source_id,),
        )
        recovered = bool(rows) and rows[0][0] == "broken"
        await db.execute(
            """INSERT INTO source_measurement_state
                (source_id, state, reason, detail, detected_at, updated_at)
            VALUES (?, 'ok', NULL, NULL, NULL, datetime('now'))
            ON CONFLICT(source_id) DO UPDATE SET
                state = 'ok', reason = NULL, detail = NULL, detected_at = NULL,
                updated_at = datetime('now')""",
            (source_id,),
        )
        await db.commit()
    if recovered:
        logger.info("Measurement state: %s -> ok (recovered)", source_id)
    return recovered


async def get_asked_at(source_id: str) -> str | None:
    """取得量の急減を本人に聞いた最終時刻。連投防止用。"""
    async with get_db_context() as db:
        rows = await db.execute_fetchall(
            "SELECT asked_at FROM source_measurement_state WHERE source_id = ?",
            (source_id,),
        )
    return rows[0][0] if rows else None


async def record_asked(source_id: str) -> None:
    async with get_db_context() as db:
        await db.execute(
            """INSERT INTO source_measurement_state (source_id, asked_at, updated_at)
            VALUES (?, datetime('now'), datetime('now'))
            ON CONFLICT(source_id) DO UPDATE SET
                asked_at = datetime('now'), updated_at = datetime('now')""",
            (source_id,),
        )
        await db.commit()


# --- 軸集計への反映（純粋関数。scoring.py / aggregation.py から共用する） ---


def category_scores(
    per_source: dict[str, list[tuple[str, float]]],
    broken: dict[str, dict],
) -> tuple[dict[str, float], list[str]]:
    """カテゴリごとに、壊れていないソースだけの平均を返す。

    per_source は {category: [(source_id, score), ...]}。
    戻り値は ({category: score}, [計測不能なカテゴリ]).

    カテゴリ内に生きているソースが1つでもあればそれで計測を続ける
    （運動=strava+oura_steps、活力=nextdns+stash が片方だけ壊れても落ちない）。
    全ソースが壊れているカテゴリだけを計測不能として外す。
    """
    scores: dict[str, float] = {}
    unknown: list[str] = []
    for category, entries in per_source.items():
        alive = [s for sid, s in entries if sid not in broken]
        if alive:
            scores[category] = sum(alive) / len(alive)
        else:
            unknown.append(category)
    return scores, sorted(unknown)


def axis_is_measurable(measured_count: int) -> bool:
    """軸スコアを出してよいだけのカテゴリが残っているか。

    計測不能が増えたときにスコアが「良く」なってはいけない。残りが少なすぎる
    なら、良い数字を出すのではなく「当てにならない」と言わせる。
    """
    return measured_count >= MIN_MEASURABLE_CATEGORIES
