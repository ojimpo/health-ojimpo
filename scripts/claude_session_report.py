#!/usr/bin/env python3
"""Claude Codeのセッション時間（分）をhealth.ojimpo.comのwebhookに送信する。

各クライアントマシンの ~/.claude/settings.json の Stop フックから呼ばれる想定。
~/.claude/projects/**/*.jsonl のタイムスタンプから当日の作業分数を推定し、
hostname と一緒にPOSTする。

環境変数:
  HEALTH_WEBHOOK_URL    送信先（例: http://localhost:8400/api/ingest/webhook/claude_session
                                     または https://health.ojimpo.com/api/ingest/webhook/claude_session）
  HEALTH_WEBHOOK_SECRET Bearer認証トークン
  CLAUDE_PROJECTS_DIR   ~/.claude/projects 以外を使う場合（任意）

5分以上イベント間隔が空いたら離席とみなす（IDLE_THRESHOLD_SECONDS）。
冪等性: 当日の累積分数を毎回送る。サーバー側はMAXで更新するので何度呼ばれてもOK。
"""

from __future__ import annotations

import json
import os
import pathlib
import socket
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone

IDLE_THRESHOLD_SECONDS = 5 * 60


def iter_timestamps(claude_dir: pathlib.Path):
    """当日の作業時間集計に必要な最近のJSONLだけを舐める（高速化）。"""
    if not claude_dir.exists():
        return
    # 当日の集計には48時間以内に更新されたファイルだけで十分
    cutoff = datetime.now(timezone.utc).timestamp() - 48 * 3600
    for jsonl in claude_dir.rglob("*.jsonl"):
        try:
            if jsonl.stat().st_mtime < cutoff:
                continue
        except OSError:
            continue
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
            continue


def compute_daily_minutes(claude_dir: pathlib.Path) -> dict[str, float]:
    timestamps = sorted(iter_timestamps(claude_dir))
    daily: dict[str, float] = defaultdict(float)
    prev: datetime | None = None
    for ts in timestamps:
        if prev is not None:
            gap = (ts - prev).total_seconds()
            if 0 < gap <= IDLE_THRESHOLD_SECONDS:
                local = ts.astimezone()
                date_str = local.strftime("%Y-%m-%d")
                daily[date_str] += gap / 60.0
        prev = ts
    return dict(daily)


def post_minutes(url: str, secret: str | None, date_str: str, minutes: float, host: str) -> None:
    payload = json.dumps({"date": date_str, "minutes": round(minutes, 1), "host": host}).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "health-ojimpo-hook/1.0"},
        method="POST",
    )
    if secret:
        req.add_header("Authorization", f"Bearer {secret}")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
    except urllib.error.HTTPError as e:
        sys.stderr.write(f"webhook HTTP error: {e.code} {e.reason}\n")
    except urllib.error.URLError as e:
        sys.stderr.write(f"webhook URL error: {e.reason}\n")
    except Exception as e:
        sys.stderr.write(f"webhook error: {e}\n")


def main() -> int:
    url = os.environ.get("HEALTH_WEBHOOK_URL")
    if not url:
        sys.stderr.write("HEALTH_WEBHOOK_URL not set; skipping\n")
        return 0

    secret = os.environ.get("HEALTH_WEBHOOK_SECRET")
    claude_dir = pathlib.Path(
        os.environ.get("CLAUDE_PROJECTS_DIR", str(pathlib.Path.home() / ".claude" / "projects"))
    )
    host = os.environ.get("HEALTH_HOST_NAME") or socket.gethostname()

    daily = compute_daily_minutes(claude_dir)
    today = datetime.now().strftime("%Y-%m-%d")

    minutes_today = daily.get(today, 0.0)
    if minutes_today <= 0:
        return 0
    post_minutes(url, secret, today, minutes_today, host)
    return 0


if __name__ == "__main__":
    sys.exit(main())
