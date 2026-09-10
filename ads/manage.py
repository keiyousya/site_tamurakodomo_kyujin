#!/usr/bin/env python3
"""
Google Ads CLI マネージャー

Usage:
  python ads/manage.py campaign status        — キャンペーンのステータス確認
  python ads/manage.py campaign enable        — キャンペーンを有効化
  python ads/manage.py campaign pause         — キャンペーンを一時停止
  python ads/manage.py campaign budget <JPY>  — 日予算を変更（円単位）
  python ads/manage.py keywords list          — キーワード一覧
  python ads/manage.py keywords sync          — config.json のキーワードを同期
  python ads/manage.py ads sync               — config.json の広告文を同期
  python ads/manage.py report <days>          — 直近N日間のパフォーマンスレポート
  python ads/manage.py setup                  — config.json から初回セットアップ

環境変数または google-ads.yaml で認証情報を設定してください。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.json"


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)


def get_client():
    """Google Ads API クライアントを取得"""
    try:
        from google.ads.googleads.client import GoogleAdsClient

        return GoogleAdsClient.load_from_storage(
            str(Path(__file__).parent.parent / "google-ads.yaml")
        )
    except FileNotFoundError:
        print("エラー: google-ads.yaml が見つかりません。")
        print("プロジェクトルートに google-ads.yaml を作成してください。")
        print("参照: https://developers.google.com/google-ads/api/docs/client-libs/python/configuration")
        sys.exit(1)
    except ImportError:
        print("エラー: google-ads ライブラリがインストールされていません。")
        print("  pip install google-ads")
        sys.exit(1)


def cmd_campaign_status(client, config):
    """キャンペーンのステータスを表示"""
    ga_service = client.get_service("GoogleAdsService")
    customer_id = client.login_customer_id

    query = """
        SELECT campaign.id, campaign.name, campaign.status,
               campaign_budget.amount_micros,
               metrics.impressions, metrics.clicks, metrics.cost_micros
        FROM campaign
        WHERE campaign.name = '{name}'
        ORDER BY campaign.id
    """.format(name=config["campaign"]["name"])

    response = ga_service.search(customer_id=customer_id, query=query)

    for row in response:
        campaign = row.campaign
        metrics = row.metrics
        budget = row.campaign_budget.amount_micros / 1_000_000
        cost = metrics.cost_micros / 1_000_000
        print(f"キャンペーン: {campaign.name}")
        print(f"  ID: {campaign.id}")
        print(f"  ステータス: {campaign.status.name}")
        print(f"  日予算: ¥{budget:,.0f}")
        print(f"  表示回数: {metrics.impressions:,}")
        print(f"  クリック数: {metrics.clicks:,}")
        print(f"  費用: ¥{cost:,.0f}")


def cmd_report(client, config, days: int = 7):
    """パフォーマンスレポートを表示"""
    ga_service = client.get_service("GoogleAdsService")
    customer_id = client.login_customer_id

    query = f"""
        SELECT segments.date,
               metrics.impressions, metrics.clicks, metrics.ctr,
               metrics.average_cpc, metrics.cost_micros, metrics.conversions
        FROM campaign
        WHERE campaign.name = '{config["campaign"]["name"]}'
          AND segments.date DURING LAST_{days}_DAYS
        ORDER BY segments.date DESC
    """

    response = ga_service.search(customer_id=customer_id, query=query)

    print(f"--- 直近 {days} 日間のレポート ---")
    print(f"{'日付':<12} {'表示':>8} {'クリック':>8} {'CTR':>8} {'CPC':>8} {'費用':>10} {'CV':>6}")
    print("-" * 70)

    for row in response:
        date = row.segments.date
        m = row.metrics
        cpc = m.average_cpc / 1_000_000
        cost = m.cost_micros / 1_000_000
        print(
            f"{date:<12} {m.impressions:>8,} {m.clicks:>8,} "
            f"{m.ctr:>7.1%} ¥{cpc:>6,.0f} ¥{cost:>9,.0f} {m.conversions:>5.0f}"
        )


def cmd_show_config():
    """現在の設定を表示"""
    config = load_config()
    print("=== 広告設定 ===\n")
    print(f"キャンペーン名: {config['campaign']['name']}")
    print(f"日予算: ¥{config['campaign']['budget_micros'] / 1_000_000:,.0f}")
    print(f"ステータス: {config['campaign']['status']}")
    print(f"地域ターゲット: {', '.join(config['campaign']['geo_targets'])}")
    print(f"\n上限CPC: ¥{config['ad_group']['cpc_bid_micros'] / 1_000_000:,.0f}")

    print("\n--- キーワード ---")
    for kw in config["keywords"]:
        print(f"  [{kw['match_type']:<8}] {kw['text']}")

    print("\n--- 除外キーワード ---")
    for kw in config["negative_keywords"]:
        print(f"  [{kw['match_type']:<8}] {kw['text']}")

    print("\n--- 広告見出し ---")
    for h in config["responsive_search_ad"]["headlines"]:
        print(f"  • {h}")

    print("\n--- 広告説明文 ---")
    for d in config["responsive_search_ad"]["descriptions"]:
        print(f"  • {d}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    command = sys.argv[1]

    if command == "config":
        cmd_show_config()
        return

    config = load_config()

    if command == "campaign":
        subcommand = sys.argv[2] if len(sys.argv) > 2 else "status"
        client = get_client()
        if subcommand == "status":
            cmd_campaign_status(client, config)
        elif subcommand == "enable":
            print("キャンペーンを有効化します（未実装 — Google Ads 管理画面で設定してください）")
        elif subcommand == "pause":
            print("キャンペーンを一時停止します（未実装 — Google Ads 管理画面で設定してください）")
        elif subcommand == "budget":
            budget = int(sys.argv[3]) if len(sys.argv) > 3 else None
            if budget:
                print(f"日予算を ¥{budget:,} に変更します（未実装）")
            else:
                print("使い方: python ads/manage.py campaign budget <金額>")
    elif command == "report":
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 7
        client = get_client()
        cmd_report(client, config, days)
    elif command == "keywords":
        print("キーワード管理（Google Ads API 設定後に利用可能）")
        print("現在の設定:")
        for kw in config["keywords"]:
            print(f"  [{kw['match_type']:<8}] {kw['text']}")
    elif command == "setup":
        print("=== 初回セットアップ ===")
        print("以下の手順で Google Ads API を設定してください:\n")
        print("1. Google Ads アカウントを作成: https://ads.google.com")
        print("2. API 開発者トークンを取得:")
        print("   https://developers.google.com/google-ads/api/docs/get-started/dev-token")
        print("3. OAuth2 認証情報を作成:")
        print("   https://console.cloud.google.com/apis/credentials")
        print("4. google-ads.yaml をプロジェクトルートに作成:")
        print('   developer_token: "YOUR_TOKEN"')
        print('   client_id: "YOUR_CLIENT_ID"')
        print('   client_secret: "YOUR_CLIENT_SECRET"')
        print('   refresh_token: "YOUR_REFRESH_TOKEN"')
        print("5. python ads/manage.py config で設定を確認")
        print("6. python ads/manage.py campaign status でステータスを確認")
    else:
        print(f"不明なコマンド: {command}")
        print(__doc__)


if __name__ == "__main__":
    main()
