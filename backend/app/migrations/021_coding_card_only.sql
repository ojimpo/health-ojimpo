-- coding カテゴリ（Claude Code, GitHub）をグラフ・文化スコアから除外し、カード表示のみにする
-- 理由: claude のトークン量がスケール破壊的（他カテゴリの10-20倍）で積み上げグラフが機能しなくなる
UPDATE source_settings SET display_type = 'card_only' WHERE name IN ('Claude Code', 'GitHub', 'OpenAI');
