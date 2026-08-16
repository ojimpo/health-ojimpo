-- Stash vitality: 再生回数(play_count)から実再生時間(play_duration)ベースへ移行
--
-- play_count は「1回開いた」しか表さないので、30分きっちり観た日と 5 秒で閉じた日が
-- 同じ 1 play になる。実際 2026-08-13 は play_count=1（=ほぼ最低点）だが実再生は 22 分あった。
-- Stash は Scene.play_duration に累積再生秒数を持っているのでこれを日次に按分する。

ALTER TABLE stash_vitality ADD COLUMN play_seconds REAL NOT NULL DEFAULT 0;

-- play_duration は「シーン単位の累積値」で、1回の再生ごとの長さは Stash に残らない。
-- そこで ingest ごとにシーン単位のスナップショットを取り、前回との差分（=前回 ingest 以降に
-- 実際に観た秒数）だけを、その間に増えた play_history の日付へ配分する。
-- ingest は1時間毎なので日付の取り違えはほぼ起きない。
CREATE TABLE IF NOT EXISTS stash_scene_state (
    scene_id TEXT PRIMARY KEY,
    play_duration REAL NOT NULL DEFAULT 0,
    play_count INTEGER NOT NULL DEFAULT 0,
    last_history_at TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 基準値の再較正（単位が plays → min に変わるため遡及的に置き換える）。
-- 2026-03〜08 の週次実再生時間の中央値が 181 分だったので 180 min/週を基準=100点とする。
-- 旧基準の 70 plays/週 は実測中央値 39 plays/週 の約1.8倍で、
-- 通常の週でも常時 56 点しか出ない過大な基準だった（vitality が慢性的に低かった主因）。
UPDATE baseline_history
SET base_value = 180,
    base_unit = 'min',
    memo = '実再生時間ベースへ移行。2026-03〜08の週次中央値181分。旧値70plays/週は実測中央値39playsに対し過大で常時低スコアだった'
WHERE source_id = 'stash_vitality';

UPDATE source_settings
SET base_value = 180,
    base_unit = 'min',
    name = 'Vitality (Stash)'
WHERE id = 'stash_vitality';
