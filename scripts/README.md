# scripts

各クライアントマシンから Claude Code のセッション時間（分）を `health-ojimpo` バックエンドに送信するためのスクリプト群。

## 仕組み

1. Claude Code の **Stop hook**（応答完了時に発火）が下記スクリプトを呼ぶ
2. スクリプトが `~/.claude/projects/**/*.jsonl` のタイムスタンプを集計し、当日のセッション時間を推定
3. セッション切れ判定は **5分**（連続イベント間隔が 5分以下なら同一セッションとして加算）
4. `POST /api/ingest/webhook/claude_session` に `{date, minutes, host}` を Bearer 認証で送信
5. サーバー側は `host` 単位で保存し、`date` 単位で合算してダッシュボードに反映（冪等：MAX で更新）

## ファイル

- [`claude_session_report.py`](claude_session_report.py) — 集計と POST 送信を行う Python 本体
- [`claude_session_report.sh`](claude_session_report.sh) — arigato-nas 用のラッパー。リポジトリの `.env` から `WEBHOOK_SECRET` を読み込んで Python を起動する

## arigato-nas（このサーバー自身）でのセットアップ

すでに設定済みです。`~/.claude/settings.json` に以下が入っています:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "nohup /home/kouki/dev/health-ojimpo/scripts/claude_session_report.sh >/dev/null 2>&1 &"
          }
        ]
      }
    ]
  }
}
```

## 他端末（Mac / iPad / 他 Linux 等）でのセットアップ

### 1. スクリプトを配置

リポジトリを clone するか、`claude_session_report.py` 単体を任意のパスに置く。

```bash
mkdir -p ~/.local/bin
curl -o ~/.local/bin/claude_session_report.py \
  https://raw.githubusercontent.com/ojimpo/health-ojimpo/master/scripts/claude_session_report.py
chmod +x ~/.local/bin/claude_session_report.py
```

### 2. ラッパーを作成

`.env` を持たない他端末では、URL とシークレットを直接指定するラッパーを作る。

```bash
cat > ~/.local/bin/claude_session_report.sh <<'EOF'
#!/bin/bash
export HEALTH_WEBHOOK_URL="https://health.ojimpo.com/api/ingest/webhook/claude_session"
export HEALTH_WEBHOOK_SECRET="（arigato-nas の .env の WEBHOOK_SECRET と同じ値）"
# host 名を明示したい場合は指定（未指定時は socket.gethostname() が使われる）
# export HEALTH_HOST_NAME="kouki-macbook"
exec python3 ~/.local/bin/claude_session_report.py
EOF
chmod +x ~/.local/bin/claude_session_report.sh
```

`/api/ingest/webhook*` は Cloudflare Access 保護対象外なので、Bearer 認証のみで外部端末から到達可能です。

### 3. Claude Code の Stop hook に登録

`~/.claude/settings.json` を編集して `hooks.Stop` を追加する（既存の設定がある場合はマージ）。

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "nohup ~/.local/bin/claude_session_report.sh >/dev/null 2>&1 &"
          }
        ]
      }
    ]
  }
}
```

`nohup ... &` でバックグラウンド実行することで、Claude Code 本体の応答に遅延が出ないようにする。

### 4. 動作確認

Claude Code でなにかしら 1 ターン会話したあと、サーバー側で記録を確認:

```bash
docker exec health-backend python -c "
import sqlite3
con = sqlite3.connect('/app/data/health.db')
for row in con.execute('SELECT date, host, minutes FROM claude_session_minutes ORDER BY date DESC LIMIT 5'):
    print(row)
"
```

新しい `host` 名でレコードが入っていれば成功。

## 環境変数

| 変数 | 必須 | 説明 |
|------|-----|------|
| `HEALTH_WEBHOOK_URL` | Yes | 送信先 URL（例: `http://localhost:8400/api/ingest/webhook/claude_session` または `https://health.ojimpo.com/api/ingest/webhook/claude_session`） |
| `HEALTH_WEBHOOK_SECRET` | Yes | Bearer 認証トークン（サーバーの `.env` の `WEBHOOK_SECRET` と同じ値） |
| `HEALTH_HOST_NAME` | - | 送信元識別子。未指定時は `socket.gethostname()` |
| `CLAUDE_PROJECTS_DIR` | - | Claude Code の projects ディレクトリ。未指定時は `~/.claude/projects` |

## 過去分のバックフィル

新しい端末を追加した直後、過去の JSONL 分を遡って入れたい場合:

```bash
# 端末上で（環境変数をセットした上で）
python3 ~/.local/bin/claude_session_report.py
```

スクリプトは「当日分のみ」を送るので、過去日全部を一括投入したい場合はスクリプトの `main()` を一時的に書き換えるか、サーバー側で `compute_daily_session_minutes()` を直接呼ぶ運用になる（arigato-nas は初回起動時にこの方式で 43 日分を一括投入済み）。
