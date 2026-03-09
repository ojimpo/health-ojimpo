# kashidashi — 図書館貸出資料管理アプリ 設計プラン

## 概要

図書館で借りた資料（CD、本、DVDなど）を記録・管理するセルフホスト型Webアプリ。
`arigato-nas`上で動作し、データの入出力はすべてAPI経由で行う。

### 設計思想

- **アプリはデータストアとビューに徹する**: スクレイピング、紐づけ、リマインドなどのロジックは外部エージェント（OpenClaw等）やプログラムがAPI経由で行う
- **AIエージェントフレンドリーなAPI**: 人間がUIから操作するのもAIエージェントがAPIを叩くのも同じインターフェース
- **段階的に育てる**: 将来的に他のアプリ（Last.fm同期、ダッシュボード等）が `kashidashi` のAPIを呼んでデータを取得できる構成
- **技術スタックはClaude Codeにお任せ**: このドキュメントでは仕様のみ定義する

---

## データモデル

### items テーブル（貸出資料）

| フィールド | 型 | 説明 |
|---|---|---|
| id | INTEGER (PK) | 自動採番 |
| type | TEXT | 資料種別: `cd`, `book`, `dvd`, `other` |
| title | TEXT | 資料タイトル（図書館サイトから取得） |
| artist | TEXT | アーティスト名（CD/DVDで使用、図書館サイトから取得） |
| author | TEXT | 著者名（本で使用、図書館サイトから取得） |
| library | TEXT | 図書館名（デフォルト: `葛飾区立中央図書館`） |
| borrowed_date | DATE | 貸出日 |
| due_date | DATE | 返却期限 |
| returned_at | DATETIME | 返却完了日時（NULL = 未返却） |
| ripped_at | DATETIME | リッピング完了日時（NULL = 未リッピング、CDのみ使用） |
| image_url | TEXT | ジャケット画像 / 書影のURL |
| musicbrainz_release_id | TEXT | MusicBrainz Release ID（CDのみ、リッピング時にCDメタデータサービスから取得） |
| isbn | TEXT | ISBN（本のみ、図書館ページまたは検索で取得） |
| tmdb_id | TEXT | TMDb ID（DVDのみ、検索で取得） |
| metadata_artist | TEXT | CDメタデータサービス（MusicBrainz等）由来のアーティスト名（CDのみ） |
| metadata_album | TEXT | CDメタデータサービス（MusicBrainz等）由来のアルバム名（CDのみ） |
| notes | TEXT | 自由メモ |
| created_at | DATETIME | レコード作成日時 |
| updated_at | DATETIME | レコード更新日時 |

### 備考

- リッピング関連フィールド（`ripped_at`, `musicbrainz_release_id`, `metadata_artist`, `metadata_album`）はCDのみ使用。`isbn` は本のみ、`tmdb_id` はDVDのみ使用。該当しないものはNULLのまま
- `artist`（図書館由来）と `metadata_artist`（CDメタデータサービス由来）を両方持つことで、表記ゆれがあっても元データを保持できる
- 将来、Last.fmデータとの紐づけには `musicbrainz_release_id` をキーに使う想定

---

## API設計

ベースパス: `/api/items`

### 資料の登録

```
POST /api/items
```

リクエストボディ:

```json
{
  "type": "cd",
  "title": "アルバムタイトル",
  "artist": "アーティスト名",
  "library": "葛飾区立中央図書館",
  "borrowed_date": "2026-03-01",
  "due_date": "2026-03-15",
  "image_url": "https://..."
}
```

- `library` は省略時デフォルト値を使用
- 同一資料の重複登録を防ぐため、`title` + `artist`/`author` + `borrowed_date` の組み合わせで重複チェック

### 資料の一覧取得

```
GET /api/items
```

クエリパラメータ（すべてオプション）:

| パラメータ | 説明 | 例 |
|---|---|---|
| type | 資料種別でフィルタ | `?type=cd` |
| status | ステータスでフィルタ | `?status=not_ripped`, `?status=not_returned`, `?status=ripped`, `?status=returned` |
| library | 図書館名でフィルタ | `?library=葛飾区立中央図書館` |
| artist | アーティスト名で検索（CD/DVD） | `?artist=スピッツ` |
| author | 著者名で検索（本） | `?author=村上春樹` |
| sort | ソート順 | `?sort=borrowed_date_desc`（デフォルト） |

### 資料の詳細取得

```
GET /api/items/{id}
```

### 資料の更新

```
PATCH /api/items/{id}
```

任意のフィールドを更新可能。

### リッピング完了の記録

```
PATCH /api/items/{id}
```

```json
{
  "ripped_at": "2026-03-01T15:30:00",
  "musicbrainz_release_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "metadata_artist": "Artist Name",
  "metadata_album": "Album Name"
}
```

- OpenClawが未リッピングのCD一覧を `GET /api/items?type=cd&status=not_ripped` で取得し、リッピング時に取得したメタデータとファジーマッチして該当するCDの `id` を特定してからこのエンドポイントを叩く
- マッチングロジックはアプリ側には持たない（OpenClaw側の責務）

### 返却完了の記録

```
PATCH /api/items/{id}
```

```json
{
  "returned_at": "2026-03-10T12:00:00"
}
```

### 資料の削除

```
DELETE /api/items/{id}
```

---

## フロントエンド

### テーブル表示

- 全資料を行形式で一覧表示（タイトル、アーティスト/著者、種別、貸出日、返却期限、ステータス等）
- フィルタ・ソート機能あり（タイル表示と同様）
- デフォルトの一覧表示として使用

### タイル表示

- 全資料をカード形式で一覧表示
- ジャケット画像 / 書影を表示（`image_url` がない場合はプレースホルダー）
- フィルタ機能:
  - 種別（CD / 本 / DVD / すべて）
  - ステータス（未リッピング / リッピング済 / 未返却 / 返却済 / すべて）
- 本も含めた全資料を表示可能

### カレンダー（ガントチャート）表示

- 貸出日〜返却日（未返却の場合は返却期限）を横棒で表示
- 月表示と週表示を切り替え可能
- 資料種別で色分け（CD、本、DVD等）

---

## 運用フロー

### 新規貸出時

1. OpenClawが図書館HPの貸出ページをスクレイピング
2. 貸出中の資料を取得（CD、本、DVD問わず全件）
3. 資料の種別を判断
4. 画像をネット検索やCDメタデータサービスから取得
5. `POST /api/items` で登録（重複チェックあり）

### リッピング時（CDのみ）

1. OpenClawがCDをリッピング（OpenClawスキル）
2. CDメタデータサービス（MusicBrainz等）からメタデータを取得（FLACファイルに埋め込み済み）
3. `GET /api/items?type=cd&status=not_ripped` で未リッピングCD一覧を取得（通常4枚以内）
4. 取得済みメタデータと図書館タイトルをファジーマッチして対象を特定
5. `PATCH /api/items/{id}` でリッピング完了とメタデータを記録

### 返却時

1. OpenClawまたはUI上で `PATCH /api/items/{id}` に `returned_at` を記録

---

## APIドキュメント

- FastAPIの自動生成ドキュメント（`/docs` Swagger UI、`/openapi.json`）を活用する
- 各エンドポイント・リクエスト/レスポンスモデルにdocstringを丁寧に記述すること
- 人間がブラウザで `/docs` を見てAPIの全体像を把握できるように、またOpenClaw等のAIエージェントが `/openapi.json` を読んで操作方法を理解できるようにする
- エンドポイントの説明には、どういう場面で使うか（例:「リッピング完了時にCDメタデータサービスから取得したメタデータとともに呼び出す」）も含める

---

## インフラ

- `arigato-nas` 上で動作（Ubuntu/Debian、N150、16GB RAM）
- Dockerコンテナとして構築（既存コンテナのポートと競合しないよう、デプロイ時にサーバー上のコンテナ状況を確認すること）
- Tailscaleネットワーク内からアクセス可能
- Cloudflare Tunnel + `ojimpo.com` で外部からもアクセス可能にする（サブドメイン形式かパス形式かは未定）
- 認証: Cloudflare Tunnel経由のアクセスには認証を設定（Cloudflare Accessまたはアプリ側での認証。方式はClaude Codeにお任せ）
- DB: SQLite（WALモード有効）
- 将来的にスクレイピングをプログラム化する場合はcronで定期実行に置き換え可能

---

## 将来の拡張ポイント

- Last.fmスクロブルデータとの紐づけ（`musicbrainz_release_id` 経由）
- 読書管理アプリとの連携（`isbn` 経由）
- 統合ダッシュボードから `/api/items` を参照
- 返却期限リマインド（外部エージェントがAPIから期限を取得して通知）
- 他の図書館への対応（`library` フィールドで区別済み）
