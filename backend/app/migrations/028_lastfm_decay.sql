-- 028: lastfm に decay_half_life=7 を設定して音楽グラフを平滑化
-- 1日単位で見ると 100〜400% の幅で激しくギザギザ → 7日減衰で平滑化
-- 他の 7日系ソース（strava, kashidashi_cd, spotify_podcast, claude）と同じ扱い
UPDATE source_settings SET decay_half_life = 7 WHERE id = 'lastfm';
