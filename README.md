# Cultural Health Dashboard

日常の文化的活動データを自動収集・スコア化し、メンタルヘルスの変化を早期に察知するためのダッシュボード。

**稼働中のデモ**: [health.ojimpo.com](https://health.ojimpo.com)

## 作った背景

音楽を聴く時間が減った。本を読まなくなった。SNSも開かなくなった——こうした「文化的活動の静かな減少」は、メンタルヘルスの悪化を示す早期シグナルになりうる。

このダッシュボードは、Last.fm、Oura Ring、Strava など複数の外部サービスから活動データを自動取得し、**入力ゼロ**で「自分の元気さ」を可視化する。本人の振り返りだけでなく、信頼できる友人にも状態を共有できる**セーフティーネット**として機能させることを目指している。

## 設計思想

### 入力ゼロ

本ダッシュボードへの直接入力は一切行わない。すべてのデータは既存の外部サービスから自動取得する。手入力が必要な時点でモチベーション維持が困難になり、最もデータが必要な「しんどい時期」にこそ入力されなくなるため。

### 2軸スコアリング

単一の「健康スコア」にまとめず、**健康指標**（NORMAL / CAUTION / CRITICAL）と**文化的指標**（RICH / MODERATE / LOW）の2軸で独立評価する。音楽を聴きまくっているが運動が止まった、など複合的な状態を正確に表現するため。

### 基準値方式

各指標に「自分にとっての"いい感じ"」を100点として基準値を設定し、そのパーセンテージでスコア化する。基準値には適用期間を持たせることで、ライフスタイルの変化（引っ越し、転職等）にも対応でき、過去のスコアが歪まない。

### イベント系ソースの指数減衰

読書・映画・ライブ・外出予定などの「90日窓で管理するイベント系ソース」には指数減衰スコアリングを適用する。従来の窓方式（N日前で急にスコアがリセットされる）を避け、過去の活動が半減期30日で自然に薄れていく挙動にすることで、グラフ上のスパイクと不自然な切断を解消している。

### 友人向け共有ビュー

健康状態に応じて演出が変化する共有ビュー。CRITICAL時にはエヴァ暴走モード風の警告演出で、友人に「最近大丈夫？」と声をかけてもらうきっかけを作る。活動の詳細は抽象化し、プライバシーを保ちつつ状態だけを伝える。

## 技術スタック

| レイヤー | 技術 |
|---------|------|
| Frontend | React (Vite) + nginx |
| Backend | FastAPI (Python) |
| Database | SQLite |
| Infra | Docker Compose |
| 外部公開 | Cloudflare Tunnel |

```
┌─────────────────────────────────────────┐
│  Cloudflare Tunnel                      │
│    ↓                                    │
│  nginx (Frontend)  ←→  FastAPI (Backend)│
│         :80               :8000         │
│                      ↓                  │
│                   SQLite                │
│                      ↑                  │
│              Scheduler (6h)             │
│                ↓                        │
│    Last.fm / Oura / Strava / ...        │
└─────────────────────────────────────────┘
```

## 対応データソース

| ソース | 取得方式 | ステータス |
|--------|---------|-----------|
| Last.fm | 公式 API | 稼働中 |
| Oura Ring | 公式 API | 稼働中 |
| Strava（ライド・通勤） | OAuth2 | 稼働中 |
| Google Calendar（外出・ライブ） | OAuth2 | 稼働中 |
| Instagram / Twitter | iOS Shortcut → Webhook | 稼働中 |
| kashidashi（図書館CD貸出） | 自作 API | 稼働中 |
| 読書メーター | sync-gateway 経由 | 稼働中 |
| Filmarks（映画） | sync-gateway 経由 | 稼働中 |
| GitHub | Fine-grained PAT | 稼働中 |
| Claude Code | ローカル JSONL 集計 | 稼働中 |
| Gmail（購買履歴） | OAuth2 | 稼働中 |
| intervals.icu | API Key | 準備中 |
| OpenAI | Admin API | 準備中 |
| Spotify Podcasts | — | Coming Soon |

全17データソースに対応予定。設定画面に全ソースが表示され、未対応のものは「Coming Soon」として表示される。

### sync-gateway について

読書メーターと Filmarks は公式 API が存在しないため、別途スクレイピングを行う [sync-gateway](https://github.com/ojimpo/sync-gateway) 経由でデータを取得する。

## セットアップ

### 前提条件

- Docker / Docker Compose
- Last.fm API キー（[https://www.last.fm/api/account/create](https://www.last.fm/api/account/create)）

### 手順

```bash
git clone https://github.com/ojimpo/health-ojimpo.git
cd health-ojimpo

# 環境変数を設定
cp .env.example .env
# .env を編集して API キーなどを入力

# 起動
docker compose up -d --build
```

ブラウザで `http://localhost:8401` にアクセス。

### 画面構成

| パス | 画面 | 説明 |
|------|------|------|
| `/` | 共有ビュー | 認証なし。友人に公開する画面 |
| `/admin` | ダッシュボード | 本人用。全データの詳細表示 |
| `/settings` | 設定 | データソース管理、基準値設定、閾値調整 |
| `/api/docs` | API ドキュメント | FastAPI 自動生成 |

## 環境変数

| 変数名 | 必須 | 説明 |
|--------|------|------|
| `APP_USERNAME` | - | ダッシュボードに表示するユーザー名 |
| `APP_DOMAIN` | - | サイトのドメイン（例: `health.example.com`） |
| `LASTFM_API_KEY` | Yes | Last.fm API キー |
| `LASTFM_USER` | Yes | Last.fm ユーザー名 |
| `FETCH_INTERVAL_HOURS` | - | データ取得間隔（デフォルト: 6時間） |
| `WEBHOOK_SECRET` | - | iOS Shortcut Webhook の Bearer トークン |
| `OURA_PERSONAL_ACCESS_TOKEN` | - | Oura Ring の Personal Access Token |
| `INTERVALS_API_KEY` | - | intervals.icu の API キー |
| `INTERVALS_ATHLETE_ID` | - | intervals.icu のアスリート ID |
| `STRAVA_CLIENT_ID` | - | Strava OAuth2 クライアント ID |
| `STRAVA_CLIENT_SECRET` | - | Strava OAuth2 クライアントシークレット |
| `GOOGLE_CLIENT_ID` | - | Google OAuth2 クライアント ID |
| `GOOGLE_CLIENT_SECRET` | - | Google OAuth2 クライアントシークレット |
| `GCAL_HOLIDAY_CALENDAR_ID` | - | 外出予定カレンダーのID（デフォルト: `primary`） |
| `GCAL_LIVE_CALENDAR_ID` | - | ライブ専用カレンダーのID |
| `SYNC_GATEWAY_BASE_URL` | - | sync-gateway の URL |
| `GITHUB_TOKEN` | - | GitHub Fine-grained PAT |
| `GITHUB_USER` | - | GitHub ユーザー名 |
| `KASHIDASHI_BASE_URL` | - | kashidashi API の URL |

## デプロイ

Docker Compose でビルド・起動し、Cloudflare Tunnel 等のリバースプロキシで外部公開する想定。`/admin` と `/settings` は認証で保護すること（Cloudflare Access など）。

```bash
docker compose up -d --build
```

コード変更後のリビルドが必要な場合：

```bash
docker compose build backend && docker compose up -d backend
```

## デザイン

ダークカラー基調にネオンカラーが映えるサイバーな雰囲気。フォントは Orbitron（見出し）+ JetBrains Mono（データ）。モックアップは `docs/mockups/` に配置。

詳細な設計ドキュメントは `docs/design.md`、スコアリングモデルの議論は `docs/notes/score-calculation-discussion.md` を参照。

## ライセンス

MIT License
