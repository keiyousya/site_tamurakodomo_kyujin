"""広告（レスポンシブ検索広告 / RSA）作成コマンド。"""

from __future__ import annotations

import click
from rich.console import Console

from ..client import (
    display_width,
    load_client,
    mutate_with_exemption,
    resolve_customer_id,
)

console = Console()


@click.group()
def ad() -> None:
    """広告（レスポンシブ検索広告）を作成する。"""


@ad.command("create-rsa")
@click.option("--ad-group-id", required=True, help="作成先の広告グループID。")
@click.option("--final-url", required=True, help="リンク先URL（広告のランディングページ）。")
@click.option(
    "--headline",
    "headlines",
    multiple=True,
    required=True,
    help="見出し（半角30字・全角15字以内）。3〜15個。複数指定する。",
)
@click.option(
    "--description",
    "descriptions",
    multiple=True,
    required=True,
    help="説明文（半角90字・全角45字以内）。2〜4個。複数指定する。",
)
@click.option("--path1", default=None, help="表示URLのパス1（半角15字以内・任意）。")
@click.option("--path2", default=None, help="表示URLのパス2（半角15字以内・任意）。")
@click.option(
    "--paused",
    is_flag=True,
    help="広告を一時停止状態で作成する（既定は有効。キャンペーンがPAUSEDなら配信はされない）。",
)
@click.option(
    "--request-exemption",
    is_flag=True,
    help="ポリシー違反で弾かれた場合に例外申請して審査に回す（求人・医療系の表現など）。",
)
@click.option("--customer-id", default=None, help="操作対象アカウントID（未指定時は.env）。")
@click.option("--yes", is_flag=True, help="確認をスキップする。")
def create_rsa(
    ad_group_id: str,
    final_url: str,
    headlines: tuple[str, ...],
    descriptions: tuple[str, ...],
    path1: str | None,
    path2: str | None,
    paused: bool,
    request_exemption: bool,
    customer_id: str | None,
    yes: bool,
) -> None:
    """レスポンシブ検索広告(RSA)を作成する。"""
    if not 3 <= len(headlines) <= 15:
        raise click.ClickException("見出し(--headline)は3〜15個指定してください。")
    if not 2 <= len(descriptions) <= 4:
        raise click.ClickException("説明文(--description)は2〜4個指定してください。")
    long_h = [h for h in headlines if display_width(h) > 30]
    long_d = [d for d in descriptions if display_width(d) > 90]
    if long_h:
        raise click.ClickException(f"半角30字超の見出しがあります: {long_h}")
    if long_d:
        raise click.ClickException(f"半角90字超の説明文があります: {long_d}")

    client = load_client()
    cid = resolve_customer_id(customer_id)

    console.print(
        f"広告グループ [bold]{ad_group_id}[/bold] にRSAを作成します"
        f"（見出し{len(headlines)} / 説明{len(descriptions)} / "
        f"{'PAUSED' if paused else 'ENABLED'}）"
    )
    if not yes:
        click.confirm("作成しますか？", abort=True)

    ag_service = client.get_service("AdGroupService")
    aga_service = client.get_service("AdGroupAdService")
    operation = client.get_type("AdGroupAdOperation")
    aga = operation.create
    aga.ad_group = ag_service.ad_group_path(cid, ad_group_id)
    aga.status = (
        client.enums.AdGroupAdStatusEnum.PAUSED
        if paused
        else client.enums.AdGroupAdStatusEnum.ENABLED
    )

    ad_obj = aga.ad
    ad_obj.final_urls.append(final_url)
    rsa = ad_obj.responsive_search_ad
    for text in headlines:
        asset = client.get_type("AdTextAsset")
        asset.text = text
        rsa.headlines.append(asset)
    for text in descriptions:
        asset = client.get_type("AdTextAsset")
        asset.text = text
        rsa.descriptions.append(asset)
    if path1:
        rsa.path1 = path1
    if path2:
        rsa.path2 = path2

    response, exempted = mutate_with_exemption(
        aga_service.mutate_ad_group_ads, cid, operation, request_exemption
    )
    note = (
        f"\n[yellow]※ 例外申請して審査に提出: {', '.join(exempted)}[/yellow]"
        if exempted
        else ""
    )
    console.print(
        f"[green]✓ RSAを作成しました。[/green]{note}\n"
        f"[dim]{response.results[0].resource_name}[/dim]"
    )
