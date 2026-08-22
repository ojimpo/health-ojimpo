-- 049: 端末の「名前」と「世代」を分離する（instance_id 追加）
--
-- これまで host 列に2つの意味が同居していた:
--   1. 人間が読む名前（どのマシンか）      → 変えたくない
--   2. 世代の識別（組み直す前か後か）      → 変えないと衝突する
-- 再構築のたびに 2 のために 1 を犠牲にして `kagi-macbook` → `kagi-macbook-2` と
-- 改名する運用になっていた（2026-08-16 のMac再構築）。その結果:
--   - 表示名に世代番号が残り続ける
--   - サーバは旧hostが「引退した」のか「フックが壊れた」のか区別できず、
--     週次ヘルスレポートが旧hostを120日間（CLAUDE_HOST_RETIRE_DAYS）鳴らし続ける
--
-- 世代を instance_id に逃がす。クライアントは初回実行時に uuid を生成して
-- ~/.local/state/health-ojimpo/instance_id に保存し、以後それを送る。端末を消して
-- 組み直せば state ごと消えるので、名前を変えなくても自動的に別世代になる。
-- サーバは「同じ host により新しい instance がいる」= 世代交代 とみなして旧世代を
-- 引退扱いにできる（時間ではなく事実で判定できる）。
--
-- 既存行は旧host文字列をそのまま世代IDとして引き継ぐ。`kagi-macbook-2` の行は
-- host を `kagi-macbook` に巻き戻し、`-2` は内部の世代IDとしてだけ残す。
-- UNIQUE を (date, host, instance_id) にするので、交代日 2026-08-16 の旧マシン分と
-- 新マシン分は両方残る（合算は従来どおり date 単位の SUM で正しい）。

DROP INDEX IF EXISTS idx_claude_session_minutes_date;

ALTER TABLE claude_session_minutes RENAME TO claude_session_minutes_old;

CREATE TABLE claude_session_minutes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    host TEXT NOT NULL,
    instance_id TEXT NOT NULL,
    minutes REAL NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    client_version TEXT,
    UNIQUE(date, host, instance_id)
);

INSERT INTO claude_session_minutes
    (date, host, instance_id, minutes, updated_at, client_version)
SELECT
    date,
    CASE WHEN host = 'kagi-macbook-2' THEN 'kagi-macbook' ELSE host END,
    host,
    minutes,
    updated_at,
    client_version
FROM claude_session_minutes_old;

DROP TABLE claude_session_minutes_old;

CREATE INDEX IF NOT EXISTS idx_claude_session_minutes_date ON claude_session_minutes(date);
CREATE INDEX IF NOT EXISTS idx_claude_session_minutes_host ON claude_session_minutes(host, instance_id, date);
