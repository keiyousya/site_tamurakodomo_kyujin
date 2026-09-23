#!/bin/bash
# Secret Manager から Google 広告の認証情報を取得して .env を作る。
# 開発者トークンと OAuth クライアントは keiyousya の MCC 配下で全サイト共通
# （web-production の google-ads/ と同じシークレット）。
# Usage: ./scripts/pull_secrets.sh

set -euo pipefail

PROJECT_ID="keiyousya-sites-prod"
ENV_FILE="$(dirname "$0")/../.env"

if [[ -f "${ENV_FILE}" ]]; then
  echo "${ENV_FILE} は既にあります。上書きする場合は削除してから再実行してください。" >&2
  exit 1
fi

echo "Pulling secrets from ${PROJECT_ID}..."

DEVELOPER_TOKEN=$(gcloud secrets versions access latest --secret=google-ads-developer-token --project="${PROJECT_ID}")
CLIENT_ID=$(gcloud secrets versions access latest --secret=google-ads-oauth-client-id --project="${PROJECT_ID}")
CLIENT_SECRET=$(gcloud secrets versions access latest --secret=google-ads-oauth-client-secret --project="${PROJECT_ID}")

cat > "${ENV_FILE}" <<ENV
GOOGLE_ADS_DEVELOPER_TOKEN=${DEVELOPER_TOKEN}
GOOGLE_ADS_CLIENT_ID=${CLIENT_ID}
GOOGLE_ADS_CLIENT_SECRET=${CLIENT_SECRET}
GOOGLE_ADS_REFRESH_TOKEN=
GOOGLE_ADS_LOGIN_CUSTOMER_ID=8532249376
GOOGLE_ADS_CUSTOMER_ID=8532249376
GOOGLE_ADS_USE_PROTO_PLUS=True
ENV

echo "Created ${ENV_FILE}"
echo ""
echo "Next:"
echo "  .venv/bin/python scripts/regen_refresh_token.py でリフレッシュトークンを発行"
