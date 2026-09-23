"""Google広告APIのリフレッシュトークンを再発行し、.env を更新する。

失効(invalid_grant)したときに使う。ブラウザでGoogle承認が必要なので
対話実行すること:

  cd ads && .venv/bin/python scripts/regen_refresh_token.py

client_id / client_secret は .env から読む。取得した refresh token は
チャット等に出さず、.env の GOOGLE_ADS_REFRESH_TOKEN 行を直接書き換える。
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
SCOPES = ["https://www.googleapis.com/auth/adwords"]


def main() -> None:
    load_dotenv(ENV_PATH)
    client_id = os.getenv("GOOGLE_ADS_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_ADS_CLIENT_SECRET")
    if not (client_id and client_secret):
        raise SystemExit("GOOGLE_ADS_CLIENT_ID / _CLIENT_SECRET が .env にありません。")

    config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }
    flow = InstalledAppFlow.from_client_config(config, scopes=SCOPES)
    print("ブラウザが開きます。広告アカウントにアクセスできるGoogleアカウントで承認してください…")
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")

    if not creds.refresh_token:
        raise SystemExit("refresh_token が返りませんでした。prompt=consent で再試行してください。")

    # .env の該当行を書き換え（他行は保持）
    # Windows は既定が cp932 になるので明示する（.env は UTF-8）
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    key = "GOOGLE_ADS_REFRESH_TOKEN"
    replaced = False
    for i, line in enumerate(lines):
        if line.startswith(key + "="):
            lines[i] = f"{key}={creds.refresh_token}"
            replaced = True
            break
    if not replaced:
        lines.append(f"{key}={creds.refresh_token}")
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("✓ .env の GOOGLE_ADS_REFRESH_TOKEN を更新しました（トークンは表示しません）。")
    print("  続けて `gads report --preset campaign --date-range LAST_7_DAYS` で疎通確認できます。")


if __name__ == "__main__":
    main()
