import json
import logging
import pathlib
from collections import defaultdict
from datetime import date, datetime, timezone

logger = logging.getLogger(__name__)

import os

CLAUDE_DIR = pathlib.Path(
    os.environ.get("CLAUDE_PROJECTS_DIR", str(pathlib.Path.home() / ".claude" / "projects"))
)


def _aggregate_from_logs() -> dict[str, dict]:
    """~/.claude/projects/**/*.jsonl からトークン使用量を日次集計する。

    ストリーミング途中の重複エントリは uuid でデデュープし、
    'server_tool_use' フィールドを持つ完了エントリのみを集計対象とする。
    """
    daily: dict[str, dict] = defaultdict(
        lambda: {
            "input_tokens": 0,
            "cache_creation_tokens": 0,
            "cache_read_tokens": 0,
            "output_tokens": 0,
        }
    )
    seen_uuids: set[str] = set()

    if not CLAUDE_DIR.exists():
        logger.warning("Claude projects directory not found: %s", CLAUDE_DIR)
        return {}

    for jsonl in CLAUDE_DIR.rglob("*.jsonl"):
        try:
            for line in jsonl.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                usage = entry.get("message", {}).get("usage", {})
                if not usage or "output_tokens" not in usage:
                    continue
                # 完了エントリのみ（server_tool_use フィールドが存在）
                if "server_tool_use" not in usage:
                    continue

                uuid = entry.get("uuid", "")
                if uuid in seen_uuids:
                    continue
                seen_uuids.add(uuid)

                timestamp = entry.get("timestamp", "")
                date_str = timestamp[:10] if timestamp else ""
                if not date_str:
                    continue

                daily[date_str]["input_tokens"] += usage.get("input_tokens", 0)
                daily[date_str]["cache_creation_tokens"] += usage.get(
                    "cache_creation_input_tokens", 0
                )
                daily[date_str]["cache_read_tokens"] += usage.get(
                    "cache_read_input_tokens", 0
                )
                daily[date_str]["output_tokens"] += usage.get("output_tokens", 0)
        except Exception:
            logger.exception("Error reading %s", jsonl)

    return daily


def fetch_daily_usage() -> list[dict]:
    """日次トークン使用量のリストを返す。

    Returns:
        List of dicts: {date, input_tokens, cache_creation_tokens,
                        cache_read_tokens, output_tokens, total_tokens}
    """
    raw = _aggregate_from_logs()
    results = []
    for date_str in sorted(raw):
        v = raw[date_str]
        total = (
            v["input_tokens"]
            + v["cache_creation_tokens"]
            + v["cache_read_tokens"]
            + v["output_tokens"]
        )
        if total == 0:
            continue
        results.append({
            "date": date_str,
            "input_tokens": v["input_tokens"],
            "cache_creation_tokens": v["cache_creation_tokens"],
            "cache_read_tokens": v["cache_read_tokens"],
            "output_tokens": v["output_tokens"],
            "total_tokens": total,
        })

    logger.info("Aggregated Claude Code usage: %d days from local logs", len(results))
    return results
