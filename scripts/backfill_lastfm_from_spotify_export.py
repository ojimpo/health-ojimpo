#!/usr/bin/env python3
"""Spotify のデータエクスポートから Last.fm 停止期間の scrobble を復元する。

背景: 2026-07-24〜2026-08-16 に Last.fm の Spotify 連携が失効し、scrobble が
ほぼ届かなかった（project_lastfm_scrobble_outage_2026_08）。Last.fm の公式 API は
約14日より古いタイムスタンプの scrobble を受け付けないため、Last.fm 側への
書き戻しはできない。代わりに privacy.spotify.com のデータエクスポートを
`lastfm_scrobbles` テーブルへ直接バックフィルする。

対応フォーマット（両方自動判別）:
- アカウントデータ（約5日で届く方）: StreamingHistory_music_*.json
  {"endTime": "2026-07-24 13:45", "artistName", "trackName", "msPlayed"}
- 拡張ストリーミング履歴（約30日）: Streaming_History_Audio_*.json
  {"ts": "2026-07-24T13:45:30Z", "master_metadata_track_name", ...}

使い方:
  # まず dry-run で件数と日別内訳を確認（既定は 2026-07-24〜2026-08-16）
  python3 scripts/backfill_lastfm_from_spotify_export.py ~/Downloads/my_spotify_data.zip
  # 問題なければ --apply
  python3 scripts/backfill_lastfm_from_spotify_export.py ~/Downloads/my_spotify_data.zip --apply

zip のまま渡せる（展開不要）。展開済みディレクトリや JSON ファイル直指定も可。

適用後は activity_records の再集計が必要だが、毎時の ingest（lastfm の
aggregate は全期間 GROUP BY）で自動的に反映されるので待つだけでよい。
すぐ反映したければ LINE リッチメニューの INGEST を押す。

注意:
- 30秒未満の再生は scrobble の慣例に合わせて除外する（--min-seconds で変更可）
- 停止期間中に Pano Scrobbler / Plex 経由で届いた少数の scrobble と二重にならないよう、
  同じ曲が ±10 分以内に既存 scrobble にあればスキップする
- アカウントデータの endTime は UTC のはずだが、万一ズレて見えたら
  --tz-offset-hours で補正できる（既存 scrobble と突き合わせて確認すること）
"""
import argparse
import json
import sys
import zipfile
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = REPO_ROOT / "data" / "health.db"

ACCOUNT_PATTERNS = ("StreamingHistory_music_", "StreamingHistory")
EXTENDED_PATTERN = "Streaming_History_Audio_"


def iter_export_entries(path: Path):
    """エクスポート（zip / ディレクトリ / JSON ファイル）から再生エントリを列挙する。"""
    if path.is_dir():
        for p in sorted(path.rglob("*.json")):
            if _is_history_file(p.name):
                yield from _load_json(p.read_text(encoding="utf-8"), p.name)
    elif path.suffix == ".zip":
        with zipfile.ZipFile(path) as zf:
            for name in sorted(zf.namelist()):
                base = Path(name).name
                if _is_history_file(base):
                    yield from _load_json(zf.read(name).decode("utf-8"), base)
    elif path.suffix == ".json":
        yield from _load_json(path.read_text(encoding="utf-8"), path.name)
    else:
        raise SystemExit(f"対応していないパスです: {path}")


def _is_history_file(name: str) -> bool:
    if name.startswith(EXTENDED_PATTERN):
        return True
    if name.startswith(ACCOUNT_PATTERNS[0]):
        return True
    # 旧形式 StreamingHistory0.json（video 等は除く）
    return name.startswith("StreamingHistory") and "video" not in name.lower()


def _load_json(text: str, filename: str):
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        print(f"[warn] {filename}: JSON parse error: {e}", file=sys.stderr)
        return
    if not isinstance(data, list):
        return
    for row in data:
        parsed = parse_entry(row)
        if parsed:
            yield parsed


def parse_entry(row: dict) -> dict | None:
    """1エントリを共通形式 {end_dt(UTC), track, artist, album, ms_played} に。"""
    if "ts" in row:  # 拡張ストリーミング履歴
        track = row.get("master_metadata_track_name")
        artist = row.get("master_metadata_album_artist_name")
        if not track or not artist:  # podcast / 動画行は track が null
            return None
        end_dt = datetime.fromisoformat(row["ts"].replace("Z", "+00:00"))
        return {
            "end_dt": end_dt.astimezone(timezone.utc),
            "track": track,
            "artist": artist,
            "album": row.get("master_metadata_album_album_name") or "",
            "ms_played": int(row.get("ms_played") or 0),
        }
    if "endTime" in row:  # アカウントデータ
        track = row.get("trackName")
        artist = row.get("artistName")
        if not track or not artist:
            return None
        end_dt = datetime.strptime(row["endTime"], "%Y-%m-%d %H:%M").replace(
            tzinfo=timezone.utc
        )
        return {
            "end_dt": end_dt,
            "track": track,
            "artist": artist,
            "album": "",
            "ms_played": int(row.get("msPlayed") or 0),
        }
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("export_path", type=Path, help="zip / ディレクトリ / JSON ファイル")
    ap.add_argument("--from", dest="date_from", default="2026-07-24")
    ap.add_argument("--to", dest="date_to", default="2026-08-16")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--min-seconds", type=int, default=30, help="これ未満の再生は除外")
    ap.add_argument("--tz-offset-hours", type=int, default=0,
                    help="endTime が UTC でなかった場合の補正（UTC = endTime - offset）")
    ap.add_argument("--apply", action="store_true", help="実際に書き込む（既定は dry-run）")
    args = ap.parse_args()

    import sqlite3

    if not args.db.exists():
        raise SystemExit(f"DB がありません: {args.db}")
    db = sqlite3.connect(args.db)

    entries = []
    seen_files = Counter()
    for e in iter_export_entries(args.export_path):
        end_dt = e["end_dt"] - timedelta(hours=args.tz_offset_hours)
        start_dt = end_dt - timedelta(milliseconds=e["ms_played"])
        day = start_dt.date().isoformat()
        if not (args.date_from <= day <= args.date_to):
            continue
        if e["ms_played"] < args.min_seconds * 1000:
            seen_files["skipped_short"] += 1
            continue
        entries.append({
            "track": e["track"],
            "artist": e["artist"],
            "album": e["album"],
            "scrobbled_at": int(start_dt.timestamp()),
            "scrobbled_date": day,
            "duration_seconds": round(e["ms_played"] / 1000),
        })

    if not entries:
        raise SystemExit(
            f"{args.date_from}〜{args.date_to} の再生が見つかりません。"
            "エクスポートの中身とファイル名パターンを確認してください。"
        )

    # 既存 scrobble（Pano/Plex 経由の残存分）との二重登録を避ける
    existing = db.execute(
        "SELECT track_name, artist_name, scrobbled_at FROM lastfm_scrobbles "
        "WHERE scrobbled_date BETWEEN ? AND ?",
        (args.date_from, args.date_to),
    ).fetchall()
    inserted, dup_near, dup_exact = [], 0, 0
    for e in entries:
        near = any(
            t.lower() == e["track"].lower()
            and a.lower() == e["artist"].lower()
            and abs(ts - e["scrobbled_at"]) < 600
            for t, a, ts in existing
        )
        if near:
            dup_near += 1
            continue
        inserted.append(e)

    daily = Counter(e["scrobbled_date"] for e in inserted)
    print(f"エクスポート内の対象再生: {len(entries)}件 "
          f"(30秒未満除外: {seen_files['skipped_short']}件, 既存と重複: {dup_near}件)")
    print(f"追加対象: {len(inserted)}件")
    for day in sorted(daily):
        print(f"  {day}: {daily[day]}件")

    if not args.apply:
        print("\n[dry-run] 書き込みは行いませんでした。問題なければ --apply を付けてください。")
        return

    cur = db.cursor()
    for e in inserted:
        r = cur.execute(
            """INSERT OR IGNORE INTO lastfm_scrobbles
            (track_name, artist_name, album_name, scrobbled_at, scrobbled_date, duration_seconds)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (e["track"], e["artist"], e["album"], e["scrobbled_at"],
             e["scrobbled_date"], e["duration_seconds"]),
        )
        if not r.rowcount:
            dup_exact += 1
    db.commit()
    print(f"\n書き込み完了: {len(inserted) - dup_exact}件 (UNIQUE 重複スキップ: {dup_exact}件)")
    print("activity_records は次回の毎時 ingest で自動再集計されます"
          "（すぐ反映したい場合は LINE リッチメニューの INGEST）。")


if __name__ == "__main__":
    main()
