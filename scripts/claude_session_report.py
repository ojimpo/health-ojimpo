#!/usr/bin/env python3
"""Claude Codeのセッション時間（分）をhealth.ojimpo.comのwebhookに送信する。

**全端末で同一のこのファイルを使う。** 端末ごとの差分は設定ファイルにのみ置き、
シェルのラッパーは作らない（v1では端末ごとに手書きの .sh があり、NAS=.env読み /
Windows=直書き / Mac=1Password と3方言に分岐して、両方サイレントに壊れた）。

設定: ~/.config/health-ojimpo/report.env （0600, KEY=VALUE, 値はクォート可）
  HEALTH_WEBHOOK_URL     送信先。既定 https://health.ojimpo.com/api/ingest/webhook/claude_session
  HEALTH_WEBHOOK_SECRET  Bearer トークン（サーバの WEBHOOK_SECRET と同じ値）
  HEALTH_HOST_NAME       端末識別子。**端末を組み直したら必ず変える**（後述）
  CLAUDE_PROJECTS_DIR    任意。既定 ~/.claude/projects
同名の環境変数があればそちらが優先される。設定ファイルはbashではなくこのスクリプトが
自前で読む（`source` させると値のクォート漏れでフックごと死ぬため）。

実行: Claude Code の Stop フックから直接呼ぶ。ラッパー不要。
  "command": "nohup python3 ~/.local/bin/claude_session_report.py >/dev/null 2>&1 &"

挙動:
- 直近48hに更新されたJSONLから日次の作業分数を推定（5分以上の間隔は離席とみなす）
- 見つかった全日付を送る。サーバはMAX更新なので再送は安全、日付をまたいでも欠けない
- 前回送信から5分未満なら送らない（Stopフックは応答のたびに発火するため）
- 成否をログに残す（~/.local/state/health-ojimpo/report.log）。v1は完全に無言で、
  arigato-nas が3ヶ月止まっていたのに誰も気付けなかった

オプション:
  --force       レート制限を無視して送る
  --dry-run     計算だけして送らない
  --all         48h制限を外して全JSONLを走査（バックフィル用）
  --since DATE  この日付以降だけ送る（--all と併用）
  --status      設定・前回送信・ログ末尾を表示（疎通確認用）
"""

from __future__ import annotations

import json
import os
import pathlib
import socket
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone

VERSION = "2"

DEFAULT_URL = "https://health.ojimpo.com/api/ingest/webhook/claude_session"
CONFIG_PATH = pathlib.Path(
    os.environ.get("HEALTH_REPORT_CONFIG", "")
    or pathlib.Path.home() / ".config" / "health-ojimpo" / "report.env"
)
STATE_DIR = pathlib.Path.home() / ".local" / "state" / "health-ojimpo"
STATE_FILE = STATE_DIR / "state.json"
LOG_FILE = STATE_DIR / "report.log"

IDLE_THRESHOLD_SECONDS = 5 * 60
MIN_INTERVAL_SECONDS = 5 * 60
LOG_MAX_BYTES = 64 * 1024


# --- 設定 -----------------------------------------------------------------

def load_config(path: pathlib.Path = CONFIG_PATH) -> dict[str, str]:
    """KEY=VALUE 形式の設定ファイルを読む。bashに解釈させない。"""
    conf: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return conf
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, sep, value = line.partition("=")
        if not sep:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        conf[key.strip()] = value
    return conf


def resolve(conf: dict[str, str], key: str, default: str = "") -> str:
    """環境変数 > 設定ファイル > 既定値。"""
    return os.environ.get(key) or conf.get(key) or default


# --- ログ・状態 ------------------------------------------------------------

def log(message: str) -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > LOG_MAX_BYTES:
            tail = LOG_FILE.read_text(encoding="utf-8", errors="replace")[-LOG_MAX_BYTES // 2:]
            LOG_FILE.write_text(tail, encoding="utf-8")
        stamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(f"{stamp} {message}\n")
    except OSError:
        pass


def read_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def write_state(state: dict) -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state), encoding="utf-8")
    except OSError:
        pass


# --- 集計 -----------------------------------------------------------------

def iter_timestamps(claude_dir: pathlib.Path, all_history: bool = False):
    """JSONLからタイムスタンプを yield する。

    既定では48時間以内に更新されたファイルだけを見る（当日分の集計にはこれで足り、
    フックが応答のたびに走るので全走査は重い）。--all で全履歴。
    """
    if not claude_dir.exists():
        log(f"claude projects dir not found: {claude_dir}")
        return
    cutoff = 0.0 if all_history else time.time() - 48 * 3600
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


def compute_daily_minutes(
    claude_dir: pathlib.Path, all_history: bool = False
) -> dict[str, float]:
    """連続イベント間隔が閾値以下の分だけ積む。日付は端末のローカル日付で割り当てる。"""
    timestamps = sorted(iter_timestamps(claude_dir, all_history))
    daily: dict[str, float] = defaultdict(float)
    prev: datetime | None = None
    for ts in timestamps:
        if prev is not None:
            gap = (ts - prev).total_seconds()
            if 0 < gap <= IDLE_THRESHOLD_SECONDS:
                daily[ts.astimezone().strftime("%Y-%m-%d")] += gap / 60.0
        prev = ts
    return dict(daily)


# --- 送信 -----------------------------------------------------------------

def post_minutes(url: str, secret: str, date_str: str, minutes: float, host: str) -> bool:
    payload = json.dumps({
        "date": date_str,
        "minutes": round(minutes, 1),
        "host": host,
        "version": VERSION,
    }).encode()
    headers = {
        "Content-Type": "application/json",
        # 独自UAは必須。CDN手前の保護がPython標準UAをスクリプト判定で弾く（403）
        "User-Agent": f"health-ojimpo-hook/{VERSION}",
    }
    if secret:
        headers["Authorization"] = f"Bearer {secret}"
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
        return True
    except urllib.error.HTTPError as e:
        log(f"POST {date_str} failed: HTTP {e.code} {e.reason}")
    except urllib.error.URLError as e:
        log(f"POST {date_str} failed: {e.reason}")
    except Exception as e:  # noqa: BLE001 — フックを絶対に落とさない
        log(f"POST {date_str} failed: {e}")
    return False


# --- エントリポイント --------------------------------------------------------

def show_status(conf: dict[str, str]) -> None:
    state = read_state()
    last = state.get("last_sent_at")
    last_str = (
        datetime.fromtimestamp(last).astimezone().strftime("%Y-%m-%d %H:%M:%S")
        if last else "なし"
    )
    secret = resolve(conf, "HEALTH_WEBHOOK_SECRET")
    print(f"version : {VERSION}")
    print(f"config  : {CONFIG_PATH} ({'あり' if CONFIG_PATH.exists() else 'なし'})")
    print(f"url     : {resolve(conf, 'HEALTH_WEBHOOK_URL', DEFAULT_URL)}")
    print(f"secret  : {'設定済み (%d文字)' % len(secret) if secret else '未設定'}")
    print(f"host    : {resolve(conf, 'HEALTH_HOST_NAME') or socket.gethostname()}")
    print(f"最終送信: {last_str}")
    if LOG_FILE.exists():
        print(f"\n--- {LOG_FILE} (末尾10行) ---")
        for line in LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()[-10:]:
            print(line)


def main(argv: list[str]) -> int:
    conf = load_config()

    if "--status" in argv:
        show_status(conf)
        return 0

    force = "--force" in argv
    dry_run = "--dry-run" in argv
    all_history = "--all" in argv
    since = ""
    if "--since" in argv:
        since = argv[argv.index("--since") + 1]

    url = resolve(conf, "HEALTH_WEBHOOK_URL", DEFAULT_URL)
    secret = resolve(conf, "HEALTH_WEBHOOK_SECRET")
    host = resolve(conf, "HEALTH_HOST_NAME") or socket.gethostname()
    claude_dir = pathlib.Path(
        resolve(conf, "CLAUDE_PROJECTS_DIR", str(pathlib.Path.home() / ".claude" / "projects"))
    )

    if not secret:
        log(f"HEALTH_WEBHOOK_SECRET 未設定（{CONFIG_PATH} を確認）。送信しません")
        return 0

    state = read_state()
    if not force and not dry_run:
        elapsed = time.time() - float(state.get("last_sent_at") or 0)
        if elapsed < MIN_INTERVAL_SECONDS:
            return 0  # 直前に送ったばかり。次のStopで送れば足りる

    daily = {d: m for d, m in compute_daily_minutes(claude_dir, all_history).items() if m > 0}
    if since:
        daily = {d: m for d, m in daily.items() if d >= since}
    if not daily:
        return 0

    if dry_run:
        for d in sorted(daily):
            print(f"{d} {daily[d]:8.1f} min  host={host}")
        print(f"\n(dry-run: {url} には送信していません)")
        return 0

    sent = [d for d in sorted(daily) if post_minutes(url, secret, d, daily[d], host)]
    if sent:
        state["last_sent_at"] = time.time()
        state["last_sent_dates"] = sent
        write_state(state)
        # 成功も残す。無言だと「止まっている」ことに気付けない
        log(f"sent {len(sent)}/{len(daily)} dates host={host} latest={sent[-1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
