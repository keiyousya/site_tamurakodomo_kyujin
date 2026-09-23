"""GoogleAdsClient の初期化と共通ヘルパ。

認証情報の読み込み順:
  1. リポジトリ直下に google-ads.yaml があればそれを使う
  2. なければ .env を読み込み、環境変数（GOOGLE_ADS_*）から構築する
"""

from __future__ import annotations

import os
import unicodedata
from functools import lru_cache
from pathlib import Path

import click
from dotenv import load_dotenv
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

# .../ads/  （pyproject や .env が置かれる場所）
ROOT = Path(__file__).resolve().parents[2]
YAML_PATH = ROOT / "google-ads.yaml"


@lru_cache(maxsize=1)
def load_client() -> GoogleAdsClient:
    """設定を読み込んで GoogleAdsClient を返す。"""
    if YAML_PATH.exists():
        return GoogleAdsClient.load_from_storage(str(YAML_PATH))

    load_dotenv(ROOT / ".env")
    missing = [
        key
        for key in (
            "GOOGLE_ADS_DEVELOPER_TOKEN",
            "GOOGLE_ADS_CLIENT_ID",
            "GOOGLE_ADS_CLIENT_SECRET",
            "GOOGLE_ADS_REFRESH_TOKEN",
        )
        if not os.getenv(key)
    ]
    if missing:
        raise click.ClickException(
            "認証情報が不足しています: "
            + ", ".join(missing)
            + "\n.env.example を .env にコピーして埋めてください（手順は README.md）。"
        )
    return GoogleAdsClient.load_from_env()


def mutate_with_exemption(mutate_fn, customer_id: str, operation, request_exemption: bool):
    """mutate を実行する。ポリシー違反で弾かれ、かつ request_exemption=True なら
    違反キーを exempt_policy_violation_keys に積んで再送（＝例外申請して審査に回す）。

    Returns: (response, exempted_policy_names)
      exempted_policy_names は例外申請したポリシー名のリスト（通常通過時は空）。
    """
    try:
        return mutate_fn(customer_id=customer_id, operations=[operation]), []
    except GoogleAdsException as ex:
        keys = [
            e.details.policy_violation_details.key
            for e in ex.failure.errors
            if e.details.policy_violation_details.key.policy_name
        ]
        if not (request_exemption and keys):
            raise
        operation.exempt_policy_violation_keys.extend(keys)
        resp = mutate_fn(customer_id=customer_id, operations=[operation])
        names = sorted({k.policy_name for k in keys})
        return resp, names


def resolve_customer_id(customer_id: str | None) -> str:
    """操作対象アカウントIDを決定する（--customer-id > 環境変数）。"""
    cid = customer_id or os.getenv("GOOGLE_ADS_CUSTOMER_ID")
    if not cid:
        raise click.ClickException(
            "操作対象アカウントIDが未指定です。"
            "--customer-id を渡すか .env の GOOGLE_ADS_CUSTOMER_ID を設定してください。"
        )
    return cid.replace("-", "").strip()


def display_width(text: str) -> int:
    """Google 広告の文字数制限で数える幅を返す（全角=2、半角=1）。

    見出しの「30文字」、説明文の「90文字」は半角換算。日本語はほぼ全角なので
    実質15文字・45文字になる。len() で数えると上限超えを見逃す。
    """
    return sum(2 if unicodedata.east_asian_width(ch) in ("F", "W") else 1 for ch in text)
