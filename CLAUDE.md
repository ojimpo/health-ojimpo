# HEALTH.OJIMPO.COM — Cultural Health Dashboard

## プロジェクト概要

日常の文化的活動（音楽、読書、映画、運動、SNS等）のデータを外部サービスから自動取得し、スコアとして数値化・可視化することで、メンタルヘルスの状態変化を早期に察知するダッシュボードアプリ。

## 重要ドキュメント

- `docs/design.md` — **設計ドキュメント v0.5**。スコアリングモデル、データソース一覧、表示仕様などの全体設計
- `docs/notes/score-calculation-discussion.md` — スコアリング議論（トークン爆発問題、指数減衰採用経緯、Curiosity軸構想）
- `docs/mockups/` — React (JSX) で書かれたUIモックアップ。デザインの方向性の参考
  - `dashboard.jsx` — 本人用ダッシュボード
  - `shared-view.jsx` — 友人用共有ビュー
  - `settings.jsx` — 設定画面

## 技術スタック

- **Frontend**: React (Vite) → nginx → port 8401
- **Backend**: FastAPI → port 8400
- **DB**: SQLite (`data/health.db`)
- **Docker Compose** で構築、自宅サーバー（arigato-nas）にデプロイ
- **Cloudflare Tunnel** 経由で `health.ojimpo.com` として公開
- フロントエンド: ダークカラー基調、ネオンカラー、サイバーな雰囲気
  - フォント: Orbitron（見出し）+ JetBrains Mono（データ）
  - グラフ: 積み上げ面グラフ + 折れ線グラフ（Recharts）

## カテゴリ設計方針

- **カテゴリラベルは4文字以内**（カテゴリカードのレイアウトが崩れるため）
- 1カテゴリに複数ソースを含むとスコアが膨らむ → 性質の異なるソースは別カテゴリに分ける
  - 例: 音楽（Last.fm）とCD貸出（kashidashi）は別カテゴリ
- **display_type** の3種:
  - `activity` — 積み上げグラフに表示、文化スコアに参加
  - `card_only` — グラフ非表示、カテゴリカードに表示、文化スコアに参加
  - `state` — CONDITIONタブの折れ線に表示
- カテゴリカラーは各サービスのブランドカラーに寄せる（Strava=オレンジ、Google Calendar=赤/紫等）
  - 色定義: `frontend/src/constants/categories.js` + DB `source_settings.color`（カード用）

## スコアリングモデル

詳細は `docs/design.md` セクション2を参照。要点:

- 各指標に「基準値」を設定し、基準値に対するパーセンテージでスコア化（100点 = 基準、上限なし）
- **指数減衰（decay_half_life）**: イベント型ソースのスパイクを平滑化（窓切断方式の代替）
- 指標分類: `baseline`（ゼロが異常）、`event`（ゼロでも正常）、`health_only`（健康スコアのみ参加）
- **集約方式**: ソース別スコア → カテゴリ内平均（カテゴリ=指標）→ 健康/文化スコア
  - 1指標に複数ソースがある場合（例: vitality = nextdns + stash）、ソースを増やしても重みは1カテゴリのまま
- **健康指標**: baseline分類カテゴリの平均 → NORMAL/CAUTION/CRITICAL
- **運動カテゴリは2ソース**: strava（意図的な運動）+ oura_steps（日常の歩数）。運動していなくても体が動いていれば健康スコアが落ちない誤検知対策（migration 038）
- **主観フィードバック**: 毎晩12:00 UTC（21:00 JST）にLINEで本人にのみ3択質問（良い/普通/悪い）→ 既存の `/api/notification/line/webhook`（follow/unfollow購読と共用）でpostback受信 → `subjective_feedback` にスコアスナップショットと共に保存（migration 039）。スコア校正の正解データ蓄積用
- **文化的指標**: display_type=activity/card_only カテゴリの平均 → RICH/MODERATE/LOW
- 総合スコアを1つにまとめない。2軸で独立して表示

## グラフ表示

- 3モードタブ: ACTIVITY / SCORE / CONDITION
- ACTIVITY: カラフル積み上げ面グラフ（デフォルト）
- SCORE: モノクロ積み上げ + 健康/文化スコア折れ線
- CONDITION: モノクロ積み上げ + sleep/readiness/stress/outing/CTL折れ線
- 粒度: 1M=日次、3M=日次、1Y=週次
- Y軸: tickを手動制御（中央値ベース）、dataMaxでスパイクも表示

## テスト

- Backend: `cd backend && python3 -m pytest`（**必ず backend/ から実行**。ルートからだと asyncio_mode 設定が効かず全asyncテストが失敗する）
- Frontend: `cd frontend && npm test`（vitest）
- スコアロジック（scoring.py / aggregation.py）を変更したら必ず pytest を回すこと
- チャートのカテゴリ定義は `backend/app/models/schemas.py` の `ACTIVITY_CATEGORIES` / `STATE_CATEGORIES` が唯一の定義箇所（ChartDataPoint はここから動的生成）

## マイグレーション

- `backend/app/migrations/` に連番SQLファイル
- init_db: duplicate column/already exists エラーを自動スキップ（冪等化）
- 最新: 039
- **コード変更はリビルドが必要**: `docker compose build backend && docker compose up -d backend`

## デプロイ

- Docker Compose で構築
- 既存コンテナのポートと競合しないよう注意
- Cloudflare Tunnel の設定は手動で行うのでアプリ側では不要

## MCPサーバー連携（health-mcp）

- `~/dev/health-mcp` — このアプリのデータを公開する読み取り専用MCPサーバー（claude.ai / Claude Code両対応）
- `GET /api/records`（`backend/app/routers/records.py`）はhealth-mcp専用に追加した生データエンドポイント（activity_recordsの日付範囲取得 + week/month集計）
- health-mcpは `/api/dashboard` `/api/settings/sources` `/api/ingest/status` `/api/records` に依存。これらのレスポンス形式やカテゴリ定義を変えたら health-mcp 側（`src/health.ts`）も確認すること
