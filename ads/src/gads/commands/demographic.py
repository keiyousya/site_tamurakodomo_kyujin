"""年齢・性別などのデモグラフィックターゲティング。"""

from __future__ import annotations

import click
from rich.console import Console
from rich.table import Table

from ..client import load_client, resolve_customer_id

console = Console()

# Google Ads の年齢セグメント（AgeRangeType enum 値）
AGE_RANGES = {
    "18-24": "AGE_RANGE_18_24",
    "25-34": "AGE_RANGE_25_34",
    "35-44": "AGE_RANGE_35_44",
    "45-54": "AGE_RANGE_45_54",
    "55-64": "AGE_RANGE_55_64",
    "65+": "AGE_RANGE_65_UP",
    "不明": "AGE_RANGE_UNDETERMINED",
}


@click.group()
def demographic() -> None:
    """年齢・性別のデモグラフィックターゲティングを設定する。"""


@demographic.command("age-list")
@click.option("--campaign-id", required=True, help="キャンペーンID。")
@click.option("--customer-id", default=None, help="操作対象アカウントID。")
def age_list(campaign_id: str, customer_id: str | None) -> None:
    """キャンペーンの年齢ターゲティング状態を表示する。"""
    client = load_client()
    cid = resolve_customer_id(customer_id)
    ga_service = client.get_service("GoogleAdsService")

    query = f"""
        SELECT
            ad_group_criterion.age_range.type,
            ad_group_criterion.negative,
            ad_group_criterion.status,
            ad_group.name
        FROM ad_group_criterion
        WHERE campaign.id = {campaign_id}
          AND ad_group_criterion.type = 'AGE_RANGE'
    """
    rows = ga_service.search(customer_id=cid, query=query)
    table = Table(title="年齢ターゲティング", title_justify="left")
    table.add_column("広告グループ")
    table.add_column("年齢層")
    table.add_column("除外")
    table.add_column("ステータス")

    count = 0
    for row in rows:
        count += 1
        age_type = row.ad_group_criterion.age_range.type_.name
        label = next(
            (k for k, v in AGE_RANGES.items() if v == age_type), age_type
        )
        table.add_row(
            row.ad_group.name,
            label,
            "除外" if row.ad_group_criterion.negative else "-",
            row.ad_group_criterion.status.name,
        )

    if count == 0:
        console.print("[dim]年齢ターゲティングは未設定です（全年齢に配信）。[/dim]")
    else:
        console.print(table)


@demographic.command("age-exclude")
@click.option("--campaign-id", required=True, help="キャンペーンID。")
@click.option(
    "--ages",
    required=True,
    multiple=True,
    type=click.Choice(list(AGE_RANGES.keys())),
    help="除外する年齢層（複数指定可）。",
)
@click.option("--customer-id", default=None, help="操作対象アカウントID。")
@click.option("--yes", is_flag=True, help="確認をスキップする。")
def age_exclude(
    campaign_id: str,
    ages: tuple[str, ...],
    customer_id: str | None,
    yes: bool,
) -> None:
    """指定した年齢層を除外する（キャンペーン単位）。"""
    client = load_client()
    cid = resolve_customer_id(customer_id)

    campaign_service = client.get_service("CampaignCriterionService")
    campaign_resource = client.get_service("CampaignService").campaign_path(
        cid, campaign_id
    )

    operations = []
    for age_label in ages:
        age_enum_name = AGE_RANGES[age_label]
        from google.ads.googleads.v25.enums.types.age_range_type import (
            AgeRangeTypeEnum,
        )

        age_enum_value = AgeRangeTypeEnum.AgeRangeType[age_enum_name]

        op = client.get_type("CampaignCriterionOperation")
        criterion = op.create
        criterion.campaign = campaign_resource
        criterion.negative = True
        criterion.age_range.type_ = age_enum_value
        operations.append(op)

    console.print(f"キャンペーン {campaign_id} から以下の年齢層を除外します:")
    for a in ages:
        console.print(f"  [red]- {a}[/red]")

    if not yes:
        click.confirm("実行しますか？", abort=True)

    response = campaign_service.mutate_campaign_criteria(
        customer_id=cid, operations=operations
    )
    console.print(
        f"[green]✓ {len(response.results)} 件の年齢除外を設定しました。[/green]"
    )


@demographic.command("age-clear")
@click.option("--campaign-id", required=True, help="キャンペーンID。")
@click.option("--customer-id", default=None, help="操作対象アカウントID。")
@click.option("--yes", is_flag=True, help="確認をスキップする。")
def age_clear(
    campaign_id: str, customer_id: str | None, yes: bool
) -> None:
    """キャンペーンの年齢除外をすべて解除する。"""
    client = load_client()
    cid = resolve_customer_id(customer_id)
    ga_service = client.get_service("GoogleAdsService")

    query = f"""
        SELECT campaign_criterion.resource_name
        FROM campaign_criterion
        WHERE campaign.id = {campaign_id}
          AND campaign_criterion.type = 'AGE_RANGE'
          AND campaign_criterion.negative = TRUE
    """
    rows = list(ga_service.search(customer_id=cid, query=query))

    if not rows:
        console.print("[dim]除外設定はありません。[/dim]")
        return

    console.print(f"[yellow]{len(rows)} 件の年齢除外を解除します。[/yellow]")
    if not yes:
        click.confirm("実行しますか？", abort=True)

    campaign_service = client.get_service("CampaignCriterionService")
    operations = []
    for row in rows:
        op = client.get_type("CampaignCriterionOperation")
        op.remove = row.campaign_criterion.resource_name
        operations.append(op)

    response = campaign_service.mutate_campaign_criteria(
        customer_id=cid, operations=operations
    )
    console.print(
        f"[green]✓ {len(response.results)} 件の年齢除外を解除しました。[/green]"
    )
