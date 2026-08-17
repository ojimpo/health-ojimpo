"""Spotify recently-played を影データとして取り込み、Last.fm の停止を即座に検知する。

2026-07 の Last.fm 事故（Spotify 連携の失効で scrobble が届かなくなり、健康スコアが
誤って CAUTION に落ちた）の再発対策。既存の取得量急減チェック
（source_health の volume_collapse）は窓が14日なので検知まで9日前後かかるが、
Spotify 側の再生記録と突き合わせれば「聴いているのに scrobble が無い」を
翌日には確定できる。

- 取り込み: /me/player/recently-played（直近50件）。spotify_podcast の OAuth トークンを
  共用する（user-read-recently-played スコープは取得済み）。ingest は毎時なので
  50件/時を超えない限り取りこぼさない。スコアには一切参加しない影データ。
- 判定: 直近2日（UTC、当日は除く）の両方で「Spotify 再生 >= 10 かつ
  Last.fm scrobble < Spotify 再生の30%」なら乖離とみなす。
- 通知: 自動では除外しない（除外の証拠は token / ingest_failed / user_reported の
  3つだけ、という measurement_state の原則を守る）。measurement_ask と同じ
  `ms:` postback で本人に LINE で確認し、「壊れてた」の回答で初めて
  user_reported として除外される。聞き直しの抑制（14日）も
  measurement_state.asked_at を共用する。

Spotify のプライベートセッションでの再生は recently-played に載らないため、
「プライベート再生だから scrobble されない」ケースは誤検知にならない。
Plex / Pano Scrobbler 経由の scrobble は Last.fm 側のカウントを増やす方向にしか
働かないので、これも誤検知側には倒れない。
"""
import logging
from datetime import datetime, timedelta, timezone

import httpx

from ..config import settings
from ..database import get_db_context
from . import measurement_state
from .line_notify import send_line_messages
from .measurement_ask import ACTION_BROKEN, ACTION_REAL, POSTBACK_PREFIX, _should_ask
from .oauth import get_valid_token

logger = logging.getLogger(__name__)

SPOTIFY_API_BASE = "https://api.spotify.com/v1"

# 監視対象。乖離が出たときの postback は measurement_ask の handler がそのまま処理する。
SOURCE_ID = "lastfm"

# その日を「判定対象」とみなす Spotify 再生数の下限。
# これ未満の日は（本当に聴いていない日と区別できないので）判定しない。
MIN_DAILY_PLAYS = 10

# Last.fm 側がこの割合を下回ったら「届いていない」とみなす。
DIVERGENCE_RATIO = 0.3

# 連続何日乖離したら聞くか。1日だと日付境界のズレ（scrobble は再生開始時刻、
# recently-played は再生終了時刻）を拾いうるので2日にしている。
CHECK_DAYS = 2


async def ingest_recent_plays() -> tuple[int, int]:
    """recently-played を取り込む。(fetched, stored) を返す。"""
    token = await get_valid_token("spotify_podcast")
    if not token:
        logger.warning("Spotify plays: no valid token")
        return 0, 0

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{SPOTIFY_API_BASE}/me/player/recently-played",
                headers={"Authorization": f"Bearer {token}"},
                params={"limit": 50},
            )
            resp.raise_for_status()
            items = resp.json().get("items", [])
    except Exception:
        logger.exception("Spotify plays: fetch failed")
        return 0, 0

    stored = await store_plays(items)
    logger.info("Spotify plays: fetched %d, stored %d new", len(items), stored)
    return len(items), stored


async def store_plays(items: list[dict]) -> int:
    stored = 0
    async with get_db_context() as db:
        for it in items:
            track = it.get("track") or {}
            played_at = it.get("played_at")
            if not played_at or not track.get("id"):
                continue
            play_date = (
                datetime.fromisoformat(played_at.replace("Z", "+00:00"))
                .astimezone(timezone.utc)
                .date()
                .isoformat()
            )
            artists = track.get("artists") or [{}]
            cur = await db.execute(
                """INSERT OR IGNORE INTO spotify_play_history
                (played_at, track_id, track_name, artist_name, duration_ms, play_date)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    played_at,
                    track["id"],
                    track.get("name", ""),
                    artists[0].get("name", ""),
                    track.get("duration_ms", 0),
                    play_date,
                ),
            )
            if cur.rowcount:
                stored += 1
        await db.commit()
    return stored


async def _daily_counts(days: list[str]) -> list[dict]:
    """各日の Spotify 再生数と Last.fm scrobble 数（どちらも UTC 日付）。"""
    out = []
    async with get_db_context() as db:
        for day in days:
            sp = await db.execute_fetchall(
                "SELECT COUNT(*) FROM spotify_play_history WHERE play_date = ?", (day,)
            )
            lf = await db.execute_fetchall(
                "SELECT COUNT(*) FROM lastfm_scrobbles WHERE scrobbled_date = ?", (day,)
            )
            out.append({"date": day, "spotify": sp[0][0], "lastfm": lf[0][0]})
    return out


def _is_diverged(stats: list[dict]) -> bool:
    return all(
        s["spotify"] >= MIN_DAILY_PLAYS and s["lastfm"] < s["spotify"] * DIVERGENCE_RATIO
        for s in stats
    )


def build_divergence_question(stats: list[dict]) -> dict:
    lines = "\n".join(
        f'{s["date"]}: Spotify {s["spotify"]}曲 / Last.fm {s["lastfm"]}件'
        for s in stats
    )
    return {
        "type": "text",
        "text": (
            "⚠️ Last.fmのスクロブラーが止まっている可能性があります。\n"
            "Spotifyでは再生があるのに、Last.fmにほとんど届いていません。\n\n"
            f"{lines}\n\n"
            "Last.fmの Settings > Applications でSpotify連携を確認してください。\n"
            "スコアの扱いはどうしますか？"
        ),
        "quickReply": {
            "items": [
                {
                    "type": "action",
                    "action": {
                        "type": "postback",
                        "label": label,
                        "data": f"{POSTBACK_PREFIX}{action}:{SOURCE_ID}",
                        "displayText": label,
                    },
                }
                for label, action in (
                    ("🔧 壊れてた（除外する）", ACTION_BROKEN),
                    ("🙂 問題ない（そのまま）", ACTION_REAL),
                )
            ]
        },
    }


async def check_lastfm_divergence(now: datetime | None = None) -> bool:
    """乖離していたら本人に LINE で確認を送る。送ったら True。"""
    if not settings.line_owner_user_id:
        return False
    if now is None:
        now = datetime.now(timezone.utc)

    broken = await measurement_state.get_broken_sources()
    if SOURCE_ID in broken:
        return False  # 既に除外済み。復帰は measurement_state 側の仕組みに任せる

    today = now.date()
    days = [(today - timedelta(days=i)).isoformat() for i in range(1, CHECK_DAYS + 1)]
    stats = await _daily_counts(days)
    if not _is_diverged(stats):
        return False

    if not _should_ask(await measurement_state.get_asked_at(SOURCE_ID), now):
        logger.info("Spotify plays: divergence detected but recently asked, skipping")
        return False

    await send_line_messages(
        settings.line_owner_user_id, [build_divergence_question(stats)]
    )
    await measurement_state.record_asked(SOURCE_ID)
    logger.warning("Spotify plays: Last.fm divergence detected, asked owner: %s", stats)
    return True
