"""config.json から検索キャンペーン一式を作成するコマンド。

予算・キャンペーン・地域・言語・除外キーワード・広告グループ・キーワード・RSA を
GoogleAdsService.Mutate の1リクエストにまとめて送る。1件でも弾かれたら全体が
ロールバックされるので、途中まで作られた残骸が残らない。

安全のためキャンペーンは PAUSED で作る。管理画面で広告の審査状況を確認してから
`gads budget status --campaign-id … --state ENABLED` で配信を始める。
"""

from __future__ import annotations

import json
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from ..client import ROOT, display_width, load_client, resolve_customer_id

console = Console()

CONFIG_PATH = ROOT / "config.json"
LANGUAGE_JAPANESE = "languageConstants/1005"

# 一時リソースID（同一リクエスト内で作成物どうしを参照するための負の番号）
TMP_BUDGET, TMP_CAMPAIGN, TMP_AD_GROUP = -1, -2, -3


def load_config(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def validate(config: dict) -> list[str]:
    """API を叩く前に分かる入稿エラーを洗い出す。"""
    errors: list[str] = []
    rsa = config["ad_group"]["responsive_search_ad"]
    if not 3 <= len(rsa["headlines"]) <= 15:
        errors.append(f"見出しは3〜15個（現在 {len(rsa['headlines'])} 個）")
    if not 2 <= len(rsa["descriptions"]) <= 4:
        errors.append(f"説明文は2〜4個（現在 {len(rsa['descriptions'])} 個）")
    for h in rsa["headlines"]:
        if display_width(h) > 30:
            errors.append(f"見出しが半角30字超（{display_width(h)}）: {h}")
    for d in rsa["descriptions"]:
        if display_width(d) > 90:
            errors.append(f"説明文が半角90字超（{display_width(d)}）: {d}")
    for key in ("path1", "path2"):
        if display_width(rsa.get(key, "")) > 15:
            errors.append(f"{key} が半角15字超: {rsa[key]}")
    return errors


def resolve_locations(client, cid: str, names: list[str]) -> dict[str, str]:
    """地域名（canonical_name）を geoTargetConstants/… に変換する。"""
    ga = client.get_service("GoogleAdsService")
    quoted = ", ".join(f"'{n}'" for n in names)
    query = f"""
        SELECT geo_target_constant.resource_name,
               geo_target_constant.canonical_name,
               geo_target_constant.target_type
        FROM geo_target_constant
        WHERE geo_target_constant.canonical_name IN ({quoted})
          AND geo_target_constant.status = ENABLED
    """
    found = {
        r.geo_target_constant.canonical_name: r.geo_target_constant.resource_name
        for r in ga.search(customer_id=cid, query=query)
    }
    missing = [n for n in names if n not in found]
    if missing:
        raise click.ClickException(
            "地域が見つかりません: "
            + ", ".join(missing)
            + "\ncanonical_name の綴りを確認してください（例: Maebashi,Gunma,Japan）。"
        )
    return found


def find_existing_campaign(client, cid: str, name: str) -> int | None:
    ga = client.get_service("GoogleAdsService")
    escaped = name.replace("'", "\\'")
    query = f"""
        SELECT campaign.id FROM campaign
        WHERE campaign.name = '{escaped}' AND campaign.status != REMOVED
    """
    rows = list(ga.search(customer_id=cid, query=query))
    return rows[0].campaign.id if rows else None


def print_plan(config: dict) -> None:
    c, ag = config["campaign"], config["ad_group"]
    rsa = ag["responsive_search_ad"]
    console.print(f"[bold]キャンペーン[/bold]: {c['name']}（検索 / 手動CPC / [green]PAUSED[/green]）")
    console.print(f"  日予算: {c['daily_budget_jpy']:,}円 / 上限CPC: {ag['cpc_jpy']:,}円")
    if "radius" in c:
        r = c["radius"]
        console.print(f"  地域（所在地のみ）: 半径 {r['km']}km（{r['lat']}, {r['lng']}）")
    else:
        console.print(f"  地域（所在地のみ）: {', '.join(c['locations'])}")
    console.print(f"  除外キーワード（フレーズ一致）: {', '.join(c['negative_keywords'])}")
    console.print(f"[bold]広告グループ[/bold]: {ag['name']}")
    console.print(f"  キーワード（フレーズ一致）: {len(ag['keywords'])} 件")
    for k in ag["keywords"]:
        console.print(f"    - {k}")

    table = Table(show_header=True, header_style="bold cyan", title="RSA")
    table.add_column("種別")
    table.add_column("テキスト")
    table.add_column("幅", justify="right")
    for h in rsa["headlines"]:
        table.add_row("見出し", h, f"{display_width(h)}/30")
    for d in rsa["descriptions"]:
        table.add_row("説明文", d, f"{display_width(d)}/90")
    console.print(table)
    console.print(f"  リンク先: {rsa['final_url']}（表示パス /{rsa.get('path1', '')}/{rsa.get('path2', '')}）")


def build_operations(client, cid: str, config: dict, geo: dict[str, str]) -> list:
    c, ag = config["campaign"], config["ad_group"]
    rsa_conf = ag["responsive_search_ad"]
    enums = client.enums
    budget_res = client.get_service("CampaignBudgetService").campaign_budget_path(cid, TMP_BUDGET)
    campaign_res = client.get_service("CampaignService").campaign_path(cid, TMP_CAMPAIGN)
    ad_group_res = client.get_service("AdGroupService").ad_group_path(cid, TMP_AD_GROUP)
    ops = []

    def new_op():
        op = client.get_type("MutateOperation")
        ops.append(op)
        return op

    # 予算
    b = new_op().campaign_budget_operation.create
    b.resource_name = budget_res
    b.name = f"{c['name']} 予算"
    b.amount_micros = c["daily_budget_jpy"] * 1_000_000
    b.delivery_method = enums.BudgetDeliveryMethodEnum.STANDARD
    b.explicitly_shared = False

    # キャンペーン（検索 / Google検索のみ / 手動CPC / PAUSED）
    camp = new_op().campaign_operation.create
    camp.resource_name = campaign_res
    camp.name = c["name"]
    camp.advertising_channel_type = enums.AdvertisingChannelTypeEnum.SEARCH
    camp.status = enums.CampaignStatusEnum.PAUSED
    camp.campaign_budget = budget_res
    camp.manual_cpc.enhanced_cpc_enabled = False
    camp.contains_eu_political_advertising = (
        enums.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING
    )
    camp.network_settings.target_google_search = True
    camp.network_settings.target_search_network = False
    camp.network_settings.target_content_network = False
    camp.network_settings.target_partner_search_network = False
    # 既定の PRESENCE_OR_INTEREST だと「前橋に関心がある」県外ユーザーにも出る。
    # 通勤圏の人だけに出したいので所在地のみにする。
    camp.geo_target_type_setting.positive_geo_target_type = (
        enums.PositiveGeoTargetTypeEnum.PRESENCE
    )

    # 地域・言語・除外キーワード（キャンペーン単位）
    if "radius" in c:
        r = c["radius"]
        cc = new_op().campaign_criterion_operation.create
        cc.campaign = campaign_res
        cc.proximity.geo_point.latitude_in_micro_degrees = int(round(r["lat"] * 1_000_000))
        cc.proximity.geo_point.longitude_in_micro_degrees = int(round(r["lng"] * 1_000_000))
        cc.proximity.radius = r["km"]
        cc.proximity.radius_units = enums.ProximityRadiusUnitsEnum.KILOMETERS
    for name in c.get("locations", []):
        cc = new_op().campaign_criterion_operation.create
        cc.campaign = campaign_res
        cc.location.geo_target_constant = geo[name]
    cc = new_op().campaign_criterion_operation.create
    cc.campaign = campaign_res
    cc.language.language_constant = LANGUAGE_JAPANESE
    for text in c["negative_keywords"]:
        cc = new_op().campaign_criterion_operation.create
        cc.campaign = campaign_res
        cc.negative = True
        cc.keyword.text = text
        # 完全一致の除外は「派遣」単体の検索しか弾かないので、フレーズ一致にする
        cc.keyword.match_type = enums.KeywordMatchTypeEnum.PHRASE

    # 広告グループ
    g = new_op().ad_group_operation.create
    g.resource_name = ad_group_res
    g.name = ag["name"]
    g.campaign = campaign_res
    g.type_ = enums.AdGroupTypeEnum.SEARCH_STANDARD
    g.cpc_bid_micros = ag["cpc_jpy"] * 1_000_000
    g.status = enums.AdGroupStatusEnum.ENABLED

    # キーワード
    for text in ag["keywords"]:
        k = new_op().ad_group_criterion_operation.create
        k.ad_group = ad_group_res
        k.status = enums.AdGroupCriterionStatusEnum.ENABLED
        k.keyword.text = text
        k.keyword.match_type = enums.KeywordMatchTypeEnum.PHRASE

    # RSA
    aga = new_op().ad_group_ad_operation.create
    aga.ad_group = ad_group_res
    aga.status = enums.AdGroupAdStatusEnum.ENABLED
    aga.ad.final_urls.append(rsa_conf["final_url"])
    rsa = aga.ad.responsive_search_ad
    for text in rsa_conf["headlines"]:
        asset = client.get_type("AdTextAsset")
        asset.text = text
        rsa.headlines.append(asset)
    for text in rsa_conf["descriptions"]:
        asset = client.get_type("AdTextAsset")
        asset.text = text
        rsa.descriptions.append(asset)
    if rsa_conf.get("path1"):
        rsa.path1 = rsa_conf["path1"]
    if rsa_conf.get("path2"):
        rsa.path2 = rsa_conf["path2"]

    return ops


@click.command()
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=CONFIG_PATH,
    show_default=True,
    help="キャンペーン設定ファイル。",
)
@click.option("--dry-run", is_flag=True, help="設定の検証と内容表示だけ行う（APIは叩かない）。")
@click.option("--customer-id", default=None, help="操作対象アカウントID（未指定時は.env）。")
@click.option("--yes", is_flag=True, help="確認をスキップする。")
def setup(config_path: Path, dry_run: bool, customer_id: str | None, yes: bool) -> None:
    """config.json から検索キャンペーン一式を PAUSED で作成する。"""
    config = load_config(config_path)
    print_plan(config)

    errors = validate(config)
    if errors:
        raise click.ClickException("設定に問題があります:\n  " + "\n  ".join(errors))
    if dry_run:
        console.print("[green]✓ 設定に問題はありません（dry-run のため作成していません）。[/green]")
        return

    client = load_client()
    cid = resolve_customer_id(customer_id)

    existing = find_existing_campaign(client, cid, config["campaign"]["name"])
    if existing:
        raise click.ClickException(
            f"同名のキャンペーンが既にあります（ID: {existing}）。"
            "作り直す場合は管理画面で削除するか、config.json の campaign.name を変えてください。"
        )

    locations = config["campaign"].get("locations", [])
    geo = resolve_locations(client, cid, locations) if locations else {}
    console.print(f"[dim]アカウント {cid} に作成します。キャンペーンは PAUSED なので配信は始まりません。[/dim]")
    if not yes:
        click.confirm("作成しますか？", abort=True)

    ops = build_operations(client, cid, config, geo)
    response = client.get_service("GoogleAdsService").mutate(
        customer_id=cid, mutate_operations=ops
    )

    ids = {}
    for r in response.mutate_operation_responses:
        for key in ("campaign_result", "ad_group_result"):
            res = getattr(r, key).resource_name
            if res:
                ids[key] = res.split("/")[-1]
    console.print(
        f"\n[green]✓ {len(ops)} 件の操作で作成しました（PAUSED）。[/green]\n"
        f"  campaign_id: [bold]{ids.get('campaign_result')}[/bold]\n"
        f"  ad_group_id: [bold]{ids.get('ad_group_result')}[/bold]\n\n"
        "[dim]次の手順:\n"
        "  1. 管理画面で広告の審査状況を確認する\n"
        f"  2. gads budget status --campaign-id {ids.get('campaign_result')} --state ENABLED[/dim]"
    )
