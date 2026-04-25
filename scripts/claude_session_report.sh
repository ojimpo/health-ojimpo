#!/bin/bash
# arigato-nas上でStopフックから呼ばれるラッパー。
# .env から WEBHOOK_SECRET を取り、localhostのwebhookに送る。
# 他端末では別のラッパー（URL/secretを直接書く形）を使う想定。

set -e

REPO_DIR="/home/kouki/dev/health-ojimpo"

# .env を読み込んで WEBHOOK_SECRET を拾う
if [ -f "$REPO_DIR/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$REPO_DIR/.env"
    set +a
fi

export HEALTH_WEBHOOK_URL="${HEALTH_WEBHOOK_URL:-http://localhost:8400/api/ingest/webhook/claude_session}"
export HEALTH_WEBHOOK_SECRET="${HEALTH_WEBHOOK_SECRET:-$WEBHOOK_SECRET}"
export HEALTH_HOST_NAME="${HEALTH_HOST_NAME:-arigato-nas}"

exec python3 "$REPO_DIR/scripts/claude_session_report.py"
