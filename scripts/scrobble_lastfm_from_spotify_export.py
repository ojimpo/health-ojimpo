#!/usr/bin/env python3
"""Spotify のデータエクスポートから、Last.fm 本体へ scrobble を書き戻す。

Last.fm の scrobble API は**約14日より古いタイムスタンプを受け付けない**
（それより古いものは無視または現在時刻に丸められる）。したがって
2026-07-24〜08-16 の停止期間のうち、**実行時点から14日以内の後半部分だけ**が
正しい日時で書き戻せる。エクスポートが届いたら1日でも早く実行すること
（1日遅れるごとに書き戻せる範囲が1日消える）。残りの前半部分は
backfill_lastfm_from_spotify_export.py でローカル DB にのみ復元する。

必要な認証情報（.env または環境変数）:
- LASTFM_API_KEY  … 既存（.env にあり）
- LASTFM_API_SECRET … https://www.last.fm/api/accounts で同じアプリの secret を確認
- LASTFM_SESSION_KEY … 下の手順で一度だけ取得（無期限に有効）

セッションキーの取得（初回のみ）:
  1. python3 scripts/scrobble_lastfm_from_spotify_export.py --get-token
     → 表示された URL をブラウザで開いて「許可」する
  2. python3 scripts/scrobble_lastfm_from_spotify_export.py --get-session <token>
     → 表示された LASTFM_SESSION_KEY を .env に追記

書き戻し:
  # dry-run（何件がまだ14日以内で書き戻せるか見る）
  python3 scripts/scrobble_lastfm_from_spotify_export.py ~/Downloads/my_spotify_data.zip
  # 実行
  python3 scripts/scrobble_lastfm_from_spotify_export.py ~/Downloads/my_spotify_data.zip --apply

- 30秒未満の再生は除外（scrobble の慣例）
- 停止期間中に Pano/Plex 経由で Last.fm に届いた分と二重にならないよう、
  ローカルミラー（health.db の lastfm_scrobbles）に同じ曲が ±10 分以内に
  あればスキップする
- 書き戻した分は次回 ingest では取れない（incremental が最新時刻からなので）。
  ローカル側は backfill スクリプトが同じ開始時刻で入れるので二重にならない。
"""
import argparse
import hashlib
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))
import backfill_lastfm_from_spotify_export as bf  # noqa: E402  (パーサを共用)

API_ROOT = "https://ws.audioscrobbler.com/2.0/"

# 公称は「2週間」。境界での丸め事故を避けるため半日のマージンを取る。
MAX_AGE = timedelta(days=13, hours=12)
BATCH = 50


def load_env(name: str) -> str:
    import os

    if os.environ.get(name):
        return os.environ[name]
    env = REPO_ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip()
    return ""


def sign(params: dict, secret: str) -> str:
    raw = "".join(f"{k}{params[k]}" for k in sorted(params)) + secret
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def api_call(method: str, params: dict, secret: str, http_post: bool = False) -> dict:
    params = {**params, "method": method}
    params["api_sig"] = sign(params, secret)
    params["format"] = "json"  # format は署名に含めない
    if http_post:
        resp = requests.post(API_ROOT, data=params, timeout=30)
    else:
        resp = requests.get(API_ROOT, params=params, timeout=30)
    data = resp.json()
    if "error" in data:
        raise SystemExit(f"Last.fm API error {data['error']}: {data.get('message')}")
    return data


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("export_path", nargs="?", type=Path)
    ap.add_argument("--get-token", action="store_true", help="認可用トークンとURLを表示")
    ap.add_argument("--get-session", metavar="TOKEN", help="承認済みトークンからセッションキーを表示")
    ap.add_argument("--from", dest="date_from", default="2026-07-24")
    ap.add_argument("--to", dest="date_to", default="2026-08-16")
    ap.add_argument("--db", type=Path, default=bf.DEFAULT_DB, help="重複チェック用ローカルミラー")
    ap.add_argument("--min-seconds", type=int, default=30)
    ap.add_argument("--tz-offset-hours", type=int, default=0)
    ap.add_argument("--apply", action="store_true", help="実際に scrobble する（既定は dry-run）")
    args = ap.parse_args()

    api_key = load_env("LASTFM_API_KEY")
    secret = load_env("LASTFM_API_SECRET")
    if (args.get_token or args.get_session or args.apply) and (not api_key or not secret):
        raise SystemExit("LASTFM_API_KEY / LASTFM_API_SECRET を .env に設定してください"
                         "（secret は https://www.last.fm/api/accounts ）")

    if args.get_token:
        data = api_call("auth.getToken", {"api_key": api_key}, secret)
        token = data["token"]
        print(f"1. このURLを開いて許可: https://www.last.fm/api/auth/?api_key={api_key}&token={token}")
        print(f"2. 許可したら: python3 {Path(__file__).name} --get-session {token}")
        return

    if args.get_session:
        data = api_call("auth.getSession", {"api_key": api_key, "token": args.get_session}, secret)
        print(f".env に追記してください:\nLASTFM_SESSION_KEY={data['session']['key']}")
        return

    session_key = load_env("LASTFM_SESSION_KEY")
    if args.apply and not session_key:
        raise SystemExit("LASTFM_SESSION_KEY が未設定です。--get-token から始めてください")
    if not args.export_path:
        raise SystemExit("エクスポートのパスを指定してください")

    # ── エクスポートを読む（backfill スクリプトのパーサを共用） ──
    now = datetime.now(timezone.utc)
    oldest_allowed = now - MAX_AGE
    entries, too_old, skipped_short = [], 0, 0
    for e in bf.iter_export_entries(args.export_path):
        end_dt = e["end_dt"] - timedelta(hours=args.tz_offset_hours)
        start_dt = end_dt - timedelta(milliseconds=e["ms_played"])
        day = start_dt.date().isoformat()
        if not (args.date_from <= day <= args.date_to):
            continue
        if e["ms_played"] < args.min_seconds * 1000:
            skipped_short += 1
            continue
        if start_dt < oldest_allowed:
            too_old += 1
            continue
        entries.append({**e, "start_ts": int(start_dt.timestamp()), "day": day})

    print(f"対象期間 {args.date_from}〜{args.date_to} / "
          f"書き戻し可能なのは {oldest_allowed.date()} 以降（14日制限）")
    print(f"書き戻し候補: {len(entries)}件 (期限切れ: {too_old}件, 30秒未満: {skipped_short}件)")
    if not entries:
        return

    # ── ローカルミラーで既存 scrobble との重複を除く ──
    import sqlite3

    if args.db.exists():
        db = sqlite3.connect(args.db)
        existing = db.execute(
            "SELECT track_name, artist_name, scrobbled_at FROM lastfm_scrobbles "
            "WHERE scrobbled_date BETWEEN ? AND ?",
            (args.date_from, args.date_to),
        ).fetchall()
        before = len(entries)
        entries = [
            e for e in entries
            if not any(
                t.lower() == e["track"].lower()
                and a.lower() == e["artist"].lower()
                and abs(ts - e["start_ts"]) < 600
                for t, a, ts in existing
            )
        ]
        if before - len(entries):
            print(f"既に Last.fm に届いている分をスキップ: {before - len(entries)}件")

    from collections import Counter

    daily = Counter(e["day"] for e in entries)
    for day in sorted(daily):
        print(f"  {day}: {daily[day]}件")

    if not args.apply:
        print("\n[dry-run] 送信していません。--apply で実行します。")
        return

    # ── 50件ずつ scrobble ──
    sent = 0
    for i in range(0, len(entries), BATCH):
        chunk = entries[i:i + BATCH]
        params = {"api_key": api_key, "sk": session_key}
        for j, e in enumerate(chunk):
            params[f"artist[{j}]"] = e["artist"]
            params[f"track[{j}]"] = e["track"]
            params[f"timestamp[{j}]"] = str(e["start_ts"])
            if e["album"]:
                params[f"album[{j}]"] = e["album"]
            params[f"duration[{j}]"] = str(round(e["ms_played"] / 1000))
        data = api_call("track.scrobble", params, secret, http_post=True)
        attr = data.get("scrobbles", {}).get("@attr", {})
        accepted = attr.get("accepted", "?")
        ignored = attr.get("ignored", "?")
        sent += len(chunk)
        print(f"  {sent}/{len(entries)} 送信 (accepted={accepted}, ignored={ignored})")
        time.sleep(1)

    print("\n完了。Last.fm のプロフィールで該当日付に入っているか確認してください。")
    print("ignored が多い場合はタイムスタンプが期限を超えています。")


if __name__ == "__main__":
    main()
