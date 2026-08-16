-- 045: Claude Codeレポータのクライアントバージョンを記録
-- 端末ごとに手書きラッパーを配っていた結果、どの端末がどの版を動かしているか
-- サーバから見えなかった。週次ヘルスレポートで古い版の端末を指摘するために持つ。
-- NULL = v1（versionを送らない旧スクリプト）。

ALTER TABLE claude_session_minutes ADD COLUMN client_version TEXT;
