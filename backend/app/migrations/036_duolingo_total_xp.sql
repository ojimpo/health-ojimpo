-- 036: duolingo を公開プロフィールAPI(ID-only, 認証不要)方式へ。
-- 公開APIは現在の totalXp スナップショットのみ返す（日次履歴は非公開）ため、
-- 日次の totalXp を保持し、前日との差分=その日のXP→分に近似する。
-- init_db は duplicate column を自動スキップするので冪等。

ALTER TABLE duolingo_daily ADD COLUMN total_xp INTEGER;
