"""予算・入札・キャンペーンON/OFFの変更コマンド。"""

from __future__ import annotations

import click
from google.api_core import protobuf_helpers
from rich.console import Console

from ..client import load_client, resolve_customer_id

console = Console()


@click.group()
def budget() -> None:
    """予算・入札・キャンペーンの状態を変更する。"""


@budget.command("set")
@click.option("--campaign-id", required=True, help="対象キャンペーンID。")
@click.option(
    "--amount",
    required=True,
    type=float,
    help="新しい日予算（円）。micros へ自動換算する。",
)
@click.option("--customer-id", default=None, help="操作対象アカウントID（未指定時は.env）。")
@click.option("--yes", is_flag=True, help="確認をスキップする。")
def set_budget(
    campaign_id: str, amount: float, customer_id: str | None, yes: bool
) -> None:
    """キャンペーンの日予算を変更する。"""
    client = load_client()
    cid = resolve_customer_id(customer_id)

    # キャンペーンに紐づく予算リソース名を取得
    ga_service = client.get_service("GoogleAdsService")
    query = f"""
        SELECT campaign.name, campaign_budget.resource_name, campaign_budget.amount_micros
        FROM campaign
        WHERE campaign.id = {campaign_id}
    """
    result = list(ga_service.search(customer_id=cid, query=query))
    if not result:
        raise click.ClickException(f"キャンペーン {campaign_id} が見つかりません。")

    row = result[0]
    budget_resource = row.campaign_budget.resource_name
    current = row.campaign_budget.amount_micros / 1_000_000
    new_micros = int(round(amount * 1_000_000))

    console.print(
        f"[bold]{row.campaign.name}[/bold] の日予算: "
        f"{current:,.0f}円 → [green]{amount:,.0f}円[/green]"
    )
    if not yes:
        click.confirm("変更しますか？", abort=True)

    budget_service = client.get_service("CampaignBudgetService")
    operation = client.get_type("CampaignBudgetOperation")
    update = operation.update
    update.resource_name = budget_resource
    update.amount_micros = new_micros
    client.copy_from(
        operation.update_mask,
        protobuf_helpers.field_mask(None, update._pb),
    )
    budget_service.mutate_campaign_budgets(customer_id=cid, operations=[operation])
    console.print("[green]✓ 予算を変更しました。[/green]")


@budget.command("status")
@click.option("--campaign-id", required=True, help="対象キャンペーンID。")
@click.option(
    "--state",
    required=True,
    type=click.Choice(["ENABLED", "PAUSED"]),
    help="キャンペーンの状態。",
)
@click.option("--customer-id", default=None, help="操作対象アカウントID（未指定時は.env）。")
@click.option("--yes", is_flag=True, help="確認をスキップする。")
def set_status(
    campaign_id: str, state: str, customer_id: str | None, yes: bool
) -> None:
    """キャンペーンを ON(ENABLED)/OFF(PAUSED) する。"""
    client = load_client()
    cid = resolve_customer_id(customer_id)

    if not yes:
        click.confirm(f"キャンペーン {campaign_id} を {state} にしますか？", abort=True)

    campaign_service = client.get_service("CampaignService")
    operation = client.get_type("CampaignOperation")
    campaign = operation.update
    campaign.resource_name = campaign_service.campaign_path(cid, campaign_id)
    campaign.status = client.enums.CampaignStatusEnum[state]
    client.copy_from(
        operation.update_mask,
        protobuf_helpers.field_mask(None, campaign._pb),
    )
    campaign_service.mutate_campaigns(customer_id=cid, operations=[operation])
    console.print(f"[green]✓ キャンペーンを {state} にしました。[/green]")
