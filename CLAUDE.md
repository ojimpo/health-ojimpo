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
- **カテゴリスコアキャップ**: 軸集約時のみ各カテゴリを200点で頭打ち（`CATEGORY_SCORE_CAP`、scoring.py + aggregation.py の2箇所）。カウント型ソースのバースト（例: X-E5で343枚/日 → 写真1080点）が軸スコアを1ヶ月支配するのを防ぐ。チャート積み上げ・カテゴリカードは生値のまま（migration 042でphoto_genka基準値も15→45に遡及再較正、3倍色つけ撤廃）
- **健康指標**: baseline分類カテゴリの平均 → NORMAL/CAUTION/CRITICAL
- **運動カテゴリは2ソース**: strava（意図的な運動）+ oura_steps（日常の歩数）。運動していなくても体が動いていれば健康スコアが落ちない誤検知対策（migration 038）
- **活力カテゴリは2ソース**: nextdns_vitality（DNSクエリ数）+ stash_vitality。**stashは実再生時間ベース**（migration 044）。再生回数だと「30分観た日」と「5秒で閉じた日」が同じ1playになり、体感と乖離していた（例: 2026-08-13は1play=ほぼ最低点だが実再生22分）。Stashは1回の再生ごとの長さを持たず `Scene.play_duration` に累積秒数しかないので、ingestごとにシーン単位のスナップショット（`stash_scene_state`）と差分を取り、増えた秒数だけを同期間に増えた `play_history` の日付へ配分する（ingestは1時間毎なので日付の取り違えはほぼ起きない）。初回だけ差分が取れないため累積値を全履歴に等分して過去日を推定。基準値は180 min/週（2026-03〜08の週次中央値181分）。旧基準70 plays/週は実測中央値39 playsの約1.8倍で、通常の週でも常時56点しか出ず活力が慢性的に低い主因だった
- **主観フィードバック**: 毎晩12:00 UTC（21:00 JST）にLINEで本人にのみ3択質問（良い/普通/悪い）→ 既存の `/api/notification/line/webhook`（follow/unfollow購読と共用）でpostback受信 → `subjective_feedback` にスコアスナップショットと共に保存（migration 039）。スコア校正の正解データ蓄積用
- **gcalの複数日イベントは日割り展開**: 旅行等は期間中の各日に1回ずつ計上（終日イベントのend_dateはexclusive扱い、時刻ありの日またぎは開始日のみ、30日で打ち切り）
- **週次ソースヘルスレポート**: 毎週日曜12:05 UTC（21:05 JST）に全アクティブソースの取得健全性を本人LINEにのみ通知（`services/source_health.py`）。OAuthトークンは実refreshで失効検知、データ途絶はbaseline系3日/event系45日で警告。プレビュー: `GET /api/notification/health-report`
  - **取得量の急減も検知する**（2026-08-16追加）。直近14日の合計が直前6窓（84日）の中央値の30%未満なら警告。存在チェックだけだと**量の崩壊が見えない**: lastfmはSpotify連携失効でscrobbleが100〜140件/日→週数件に崩壊したが、Pano Scrobbler/Plexが数日おきに数件送り続けたため「最終データ0〜2日前」で8週間ok判定だった。閾値30%は実データ16週のバックテストで決定（誤検知0、障害の9日後に検知）
  - 対象は `classification != 'event'` かつ `score_method != 'daily_avg'`。状態系(oura)のraw_valueは「量」でなくスケールも混在するため（stress 900〜2700がsleep/readiness 0〜100を飲み込む）除外。履歴が98日分揃わないソース、平常時が基準値期待量の半分未満のソースも判定しない
- **LINEリッチメニュー（手動トリガー3ボタン、本人にのみリンク・友人には非表示）**: INGEST=全ソース取り込み（テキスト「ingest」も可、多重実行ガードあり、完了サマリをpush）/ HEALTH=ソースヘルスレポート即時送信 / MOOD=調子の3択質問即時送信。`services/line_menu.py`（postback `ingest:run` / `menu:health` / `menu:subjective`）。`POST /api/ingest/trigger` はBearer認証必須（WEBHOOK_SECRET）+ `source: "all"` 対応。リッチメニュー登録: `python3 scripts/setup_line_richmenu.py`（ホストで実行）
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

## コミットの進め方

- **新機能は1コミットにまとめず、作業のまとまりごとに段階的にコミットする**
  - 理由: 複数の Claude Code セッションを同時に動かすことがあり、未コミットの変更が大きな塊で残っていると別セッションの変更と混ざって、どれが何の作業か・どこまで終わったかが分からなくなる
  - 分割の目安: マイグレーション追加 / バックエンドのロジック / API・ルーター / フロントエンド / テスト / ドキュメント
  - 各コミット時点で壊れていない状態（少なくとも `cd backend && python3 -m pytest` が通る状態）を保つ
  - 長い実装に入る前に、どういう単位でコミットしていくかの分割案を先に示す
- コミット自体はユーザーに明示的に求められた時のみ行う。承認をもらった範囲は上記のとおり細かく分けてコミットする

## マイグレーション

- `backend/app/migrations/` に連番SQLファイル
- init_db: `schema_migrations` テーブルで適用済みファイルを追跡し、各マイグレーションは1回だけ実行（2026-07-08導入。それ以前は起動ごとに全再実行され、UPDATE/DELETEのみのマイグレーションが設定やレコードを巻き戻していた）
- 最新: 044（043は `043_notification_hold.sql` で使用済みなので採番の重複に注意）
- **コード変更はリビルドが必要**: `docker compose build backend && docker compose up -d backend`

## デプロイ

- Docker Compose で構築
- 既存コンテナのポートと競合しないよう注意
- Cloudflare Tunnel の設定は手動で行うのでアプリ側では不要

## MCPサーバー連携（health-mcp）

- `~/dev/health-mcp` — このアプリのデータを公開する読み取り専用MCPサーバー（claude.ai / Claude Code両対応）
- `GET /api/records`（`backend/app/routers/records.py`）はhealth-mcp専用に追加した生データエンドポイント（activity_recordsの日付範囲取得 + week/month集計）
- health-mcpは `/api/dashboard` `/api/settings/sources` `/api/ingest/status` `/api/records` に依存。これらのレスポンス形式やカテゴリ定義を変えたら health-mcp 側（`src/health.ts`）も確認すること

## Strava のトークンは strava-autopilot（ゲートウェイ）に一元化 (2026-07-28)

このアプリと `strava-autopilot` は **同じ Strava API アプリ**（`STRAVA_CLIENT_ID/SECRET` が同一値）を共有している。
Strava は 1 アカウントにつき API アプリ 1 個で、さらに 2026-06 以降は API 利用に Strava サブスクが必要なので、
アプリごとに登録を分けることができない。

問題は**トークンのリフレッシュ**だった。両者が別々に `oauth_tokens` を持ち独立にリフレッシュすると、
Strava のリフレッシュトークンのローテーションで**片方が無効化されうる**（実際、両 DB のトークンは
`expires_at` が秒まで一致＝同じトークンをコピーして共有している状態だった）。

そこで **トークンの更新は strava-autopilot だけが行う**ことにし、こちらは都度もらうだけにした。

- `.env`: `STRAVA_GATEWAY_URL`（既定 `https://strava.ojimpo.com`）と `STRAVA_GATEWAY_API_KEY`
  （autopilot 側 `.env` の `GATEWAY_API_KEY` と同じ値）。
- `sources/strava.py` の `_get_access_token()` が `GET /api/gateway/token` からアクセストークンを取る。
  **ゲートウェイ未設定なら従来どおりローカルの `oauth_tokens` を使う**（後方互換。設定を消せば元の挙動に戻る）。
- `services/source_health.py` の `_check_token()` も strava だけゲートウェイに委譲する。
  ここは `get_valid_token` を副作用込み（期限切れならリフレッシュ）で呼ぶので、塞がないとヘルスチェックが
  トークンをローテーションさせてしまう。
- `is_configured()` はゲートウェイ設定済みなら True（ローカルトークンが無くても「設定済み」）。
- **注意**: `/api/oauth/strava/...` の再認可フローはコード上まだ残っている。ここから再認可すると
  新しい認可が発行されて系統が枝分かれし、autopilot 側を壊しうる。**Strava の再認可は autopilot 側で行うこと。**
- DB に残っている古い `oauth_tokens` の strava 行は、もう誰も更新しないので放置で構わない（参照もされない）。
