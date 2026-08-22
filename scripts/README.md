# scripts

各クライアントマシンから Claude Code のセッション時間（分）を `health-ojimpo` バックエンドに送信するためのスクリプト。

## 方針: 全端末で同一のスクリプトを使う

**端末ごとのラッパーは作りません。** 以前は端末ごとに手書きの `.sh` ラッパーがあり、
arigato-nas は `.env` 読み込み、Windows 機は値を直書き、Mac は 1Password を実行時に叩く、と
3方言に分岐していました。結果として:

- arigato-nas は `.env` に `OUTING_HOME_CITIES=Sōka Shi`（クォート無し）が入った日から、
  ラッパーの `source .env` が `Shi: command not found` で失敗し、冒頭の `set -e` で
  python に到達せず**3ヶ月間サイレントに停止**（2026-05-26〜08-16）
- Mac は `op://` 参照の vault 名・項目名が間違ったまま一度も実行検証されず停止

どちらも「端末ごとに違うシェルスクリプトを手書きした」ことに起因します。分岐点を無くすため、
**[`claude_session_report.py`](claude_session_report.py) 1本を全端末に同じ内容で置き**、
端末差分は設定ファイルにのみ置きます。設定ファイルは bash ではなく **スクリプト自身がパース**
します（`source` させると、値のクォート漏れがフックの死に直結するため）。

## 仕組み

1. Claude Code の **Stop hook**（応答完了時に発火）がスクリプトを呼ぶ
2. `~/.claude/projects/**/*.jsonl` のタイムスタンプを集計し、日次のセッション時間を推定
3. セッション切れ判定は **5分**（連続イベント間隔が 5分以下なら同一セッションとして加算）
4. `POST /api/ingest/webhook/claude_session` に `{date, minutes, host, version, instance}` を Bearer 認証で送信
5. サーバー側は `host` + `instance`（端末の世代）単位で保存し、`date` 単位で合算（冪等：`MAX` で更新）

前回送信から **5分未満なら送りません**（Stop フックは応答のたびに発火するため）。
間引きで末尾の数分が落ちても、次の送信が同じ日を再計算して `MAX` で上書きするので回復します。

## セットアップ（全端末共通）

### 1. スクリプトを配置

```bash
mkdir -p ~/.local/bin
curl -o ~/.local/bin/claude_session_report.py \
  https://raw.githubusercontent.com/ojimpo/health-ojimpo/master/scripts/claude_session_report.py
chmod +x ~/.local/bin/claude_session_report.py
```

arigato-nas（サーバー自身）も例外にせず、同じ手順・同じパスで置きます。

### 2. 設定ファイルを作る

```bash
mkdir -p ~/.config/health-ojimpo
umask 077
cat > ~/.config/health-ojimpo/report.env <<'EOF'
HEALTH_WEBHOOK_URL="https://health.ojimpo.com/api/ingest/webhook/claude_session"
HEALTH_WEBHOOK_SECRET="（サーバーの .env の WEBHOOK_SECRET と同じ値）"
HEALTH_HOST_NAME="この端末の識別子"
EOF
chmod 600 ~/.config/health-ojimpo/report.env
```

**値は必ずクォートで囲むこと。** 1Password 等で管理している場合も、実行時ではなく
**セットアップ時に1回だけ**取り出してこのファイルに置きます（Stop フックは応答のたびに
発火するので、実行時に生体認証を挟むと使い物になりません）。

arigato-nas（サーバー自身）だけは URL を `http://localhost:8400/api/ingest/webhook/claude_session`
にします。

#### `HEALTH_HOST_NAME` は明示すること

未指定だと `socket.gethostname()` が使われますが、ホスト名は OS の設定次第で変わるので、
どの端末のデータか分からなくなります。明示的に指定してください。

**組み直しても名前は変えません。** 名前は人間が読むためのもので、端末の世代は
次の `instance_id` が別に持ちます（v3 以降）。

### 端末の世代（`instance_id`）

初回実行時に `~/.local/state/health-ojimpo/instance_id` に世代 ID（uuid）を作って保存し、
以後それを送ります。**端末を消して組み直せば state ごと消えるので、名前を変えなくても
自動的に別世代になります。** サーバーは `(host, instance_id)` で行を分けるので、

- 交代日の旧マシン分と新マシン分が `MAX` 更新で潰し合わない
- 「同じ名前に新しい世代が現れた」= 旧世代は引退した、と断定できる。週次ヘルスレポートは
  旧世代を鳴らさない（v2 以前は改名した旧 host が引退か故障か区別できず、120日間
  毎週警告が出ていた）

v2 までは `kagi-macbook` → `kagi-macbook-2` と改名して世代を分けていました。migration 049 で
旧 host 文字列をそのまま世代 ID に引き継いであるので、過去のデータは名前で分かれたまま
残っています（表示名は `kagi-macbook` に戻ります）。

#### 既存端末を v2 から v3 に上げるとき

**スクリプトを置き換える前に、いまの host 名を世代 ID として書き込んでください。**

```bash
mkdir -p ~/.local/state/health-ojimpo
echo "（この端末の現在の HEALTH_HOST_NAME）" > ~/.local/state/health-ojimpo/instance_id
```

書かずに上げると新しい uuid が発行され、サーバーからは「同じ端末に新世代が現れた」
＝**その日は旧世代と新世代の両方が同じ作業時間を申告する**ことになり、二重計上されます
（合算は世代をまたいで SUM するため）。組み直した直後の端末では逆に**作ってはいけません**
（新しい世代として発行させる）。

### 3. Stop hook に登録

`~/.claude/settings.json` を編集（既存設定があればマージ）:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "nohup python3 ~/.local/bin/claude_session_report.py >/dev/null 2>&1 &"
          }
        ]
      }
    ]
  }
}
```

`nohup ... &` でバックグラウンド実行し、Claude Code 本体の応答に遅延が出ないようにします。

### 4. 疎通確認

```bash
python3 ~/.local/bin/claude_session_report.py --status    # 設定が読めているか
python3 ~/.local/bin/claude_session_report.py --dry-run   # 送らずに計算結果だけ表示
python3 ~/.local/bin/claude_session_report.py --force     # レート制限を無視して送信
```

`--status` の「最終送信」が更新されていれば成功です。失敗していれば
`~/.local/state/health-ojimpo/report.log` に理由が残ります。

## オプション

| オプション | 説明 |
|---|---|
| `--status` | 設定・最終送信時刻・ログ末尾を表示 |
| `--dry-run` | 計算だけして送信しない |
| `--force` | 5分のレート制限を無視して送る |
| `--all` | 48時間以内に更新された JSONL だけでなく全履歴を走査（バックフィル用） |
| `--since YYYY-MM-DD` | この日付以降だけ送る（`--all` と併用） |

### 過去分のバックフィル

```bash
python3 ~/.local/bin/claude_session_report.py --all --since 2026-05-01 --force
```

サーバー側は `MAX` 更新なので、既存の値より大きいときだけ上書きされます。
**Claude Code の JSONL は既定30日で削除される**ので、それより古い期間は復元できません。

## 設定項目

| 変数 | 必須 | 説明 |
|------|-----|------|
| `HEALTH_WEBHOOK_URL` | - | 送信先。既定は `https://health.ojimpo.com/api/ingest/webhook/claude_session` |
| `HEALTH_WEBHOOK_SECRET` | Yes | Bearer 認証トークン（サーバーの `.env` の `WEBHOOK_SECRET`） |
| `HEALTH_HOST_NAME` | 推奨 | 送信元識別子。未指定時は `socket.gethostname()`（上記の理由で明示推奨） |
| `CLAUDE_PROJECTS_DIR` | - | Claude Code の projects ディレクトリ。既定 `~/.claude/projects` |

同名の環境変数があれば設定ファイルより優先されます。

## 認証について

- **共有シークレット1本を全端末に配る設計**です。端末ごとにトークンを分けてはいません。
  `host` はクライアントの自己申告で、シークレットを持てば任意の host を名乗れますが、
  データが「自分のコーディング時間」なので実害がありません
- `/api/ingest/webhook*` は Cloudflare Access 保護の対象外なので、外部端末から
  Bearer 認証だけで到達できます
- Python 標準の User-Agent は CDN 手前の保護機構にスクリプト判定で弾かれる（403）ため、
  独自 UA（`health-ojimpo-hook/<version>`）を送っています。別実装を作る場合も必須です

## 止まっていることに気付く仕組み

v1 は失敗しても完全に無言で `exit 0` していたため、上記の3ヶ月停止に誰も気付けませんでした。
現在は2段構えです:

- **クライアント側**: 送信の成否を `~/.local/state/health-ojimpo/report.log` に記録
- **サーバー側**: 週次ソースヘルスレポート（日曜 21:05 JST に本人 LINE）が
  **端末ごと**に沈黙を検知する。閾値は端末ごとに自動較正（その端末の過去の送信間隔の
  中央値 × 4、最短7日・最長60日）。120日沈黙した端末は引退扱いで鳴り止む。
  現役端末が古いバージョンのスクリプトを動かしている場合も指摘する。
  **判定は端末ごとに最新世代（`instance_id`）だけを見る。** 後継世代のある古い世代は
  引退が確定しているので鳴らさず、後継の無いまま黙った端末は従来どおり鳴る

ソース単位のチェックだけでは、**1台のフックが死んでも他端末が送っていれば生きて見える**
ため気付けません（Last.fm の「データは来ているが量が崩壊」と同型の穴）。

## 記録内容の確認

```bash
docker exec health-backend python -c "
import sqlite3
con = sqlite3.connect('/app/data/health.db')
for row in con.execute('''SELECT date, host, minutes, client_version
    FROM claude_session_minutes ORDER BY date DESC LIMIT 10'''):
    print(row)
"
```
