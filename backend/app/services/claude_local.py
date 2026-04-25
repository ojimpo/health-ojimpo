import json
import logging
import os
import pathlib
from collections import defaultdict
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

CLAUDE_DIR = pathlib.Path(
    os.environ.get("CLAUDE_PROJECTS_DIR", str(pathlib.Path.home() / ".claude" / "projects"))
)

# セッション切れと判定する無操作時間（秒）
IDLE_THRESHOLD_SECONDS = 5 * 60


def _iter_jsonl_timestamps(claude_dir: pathlib.Path):
    """全JSONLからタイムスタンプ(UTC)を yield する。"""
    if not claude_dir.exists():
        logger.warning("Claude projects directory not found: %s", claude_dir)
        return

    for jsonl in claude_dir.rglob("*.jsonl"):
        try:
            for line in jsonl.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = entry.get("timestamp", "")
                if not ts:
                    continue
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except ValueError:
                    continue
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                yield dt
        except Exception:
            logger.exception("Error reading %s", jsonl)


def compute_daily_session_minutes(
    claude_dir: pathlib.Path | None = None,
    idle_threshold_seconds: int = IDLE_THRESHOLD_SECONDS,
) -> dict[str, float]:
    """JSONLのタイムスタンプから日次の作業時間（分）を推定する。

    連続するイベント間の間隔が idle_threshold_seconds 以下なら同一セッションとして
    時間を加算する。閾値を超えたら離席とみなして加算しない。
    日付はUTC基準で割り当てる（タイムスタンプの先頭10文字）。

    Returns:
        {"YYYY-MM-DD": minutes}
    """
    if claude_dir is None:
        claude_dir = CLAUDE_DIR

    timestamps = sorted(_iter_jsonl_timestamps(claude_dir))
    daily: dict[str, float] = defaultdict(float)

    prev: datetime | None = None
    for ts in timestamps:
        if prev is not None:
            gap = (ts - prev).total_seconds()
            if 0 < gap <= idle_threshold_seconds:
                date_str = ts.strftime("%Y-%m-%d")
                daily[date_str] += gap / 60.0
        prev = ts

    return dict(daily)
