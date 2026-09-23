"""コンバージョンアクション管理コマンド（一覧・作成・タグ取得）。

応募フォーム送信・電話タップのようなウェブサイト上の行動を計測するため、
WEBPAGE 型のコンバージョンアクションを作成し、設置用タグ（gtag.js の
グローバルタグ＋イベントスニペット）を取り出せるようにする。
"""

from __future__ import annotations

import click
from google.ads.googleads.errors import GoogleAdsException
from google.protobuf.field_mask_pb2 import FieldMask
from rich.console import Console
from rich.table import Table

from ..client import load_client, resolve_customer_id

console = Console()

# 作成時に選べるカテゴリ（リード系を中心に）。応募フォーム送信は SUBMIT_LEAD_FORM、電話タップは CONTACT。
CATEGORIES = [
    "SUBMIT_LEAD_FORM",
    "CONTACT",
    "BOOK_APPOINTMENT",
    "SIGNUP",
    "REQUEST_QUOTE",
    "DEFAULT",
]


@click.group()
def conversion() -> None:
    """コンバージョンアクションの一覧・作成・タグ取得を行う。"""


@conversion.command("list")
@click.option("--customer-id", default=None, help="操作対象アカウントID（未指定時は.env）。")
def list_conversions(customer_id: str | None) -> None:
    """登録済みコンバージョンアクションを一覧表示する。"""
    client = load_client()
    cid = resolve_customer_id(customer_id)

    query = """
        SELECT
          conversion_action.id,
          conversion_action.name,
          conversion_action.type,
          conversion_action.category,
          conversion_action.status,
          conversion_action.primary_for_goal
        FROM conversion_action
        ORDER BY conversion_action.name
    """
    ga_service = client.get_service("GoogleAdsService")
    rows = list(ga_service.search(customer_id=cid, query=query))
    if not rows:
        console.print("[yellow]コンバージョンアクションが見つかりませんでした。[/yellow]")
        return

    table = Table(show_header=True, header_style="bold cyan")
    for h in ("ID", "名前", "種別", "カテゴリ", "状態", "主要"):
        table.add_column(h)
    for r in rows:
        c = r.conversion_action
        table.add_row(
            str(c.id),
            c.name,
            c.type_.name,
            c.category.name,
            c.status.name,
            "✓" if c.primary_for_goal else "",
        )
    console.print(table)


@conversion.command("create")
@click.option("--name", required=True, help="コンバージョンアクション名（例: 応募フォーム送信）。")
@click.option(
    "--category",
    type=click.Choice(CATEGORIES),
    default="SUBMIT_LEAD_FORM",
    show_default=True,
    help="コンバージョンのカテゴリ。",
)
@click.option(
    "--counting",
    type=click.Choice(["ONE_PER_CLICK", "MANY_PER_CLICK"]),
    default="ONE_PER_CLICK",
    show_default=True,
    help="カウント方法。リードは ONE_PER_CLICK（1クリックにつき1件）が無難。",
)
@click.option(
    "--value",
    type=float,
    default=None,
    help="1件あたりの既定の価値（円）。省略時は価値なし。",
)
@click.option(
    "--no-primary",
    is_flag=True,
    help="主要コンバージョン（最適化対象）にしない（副次として作成）。",
)
@click.option("--customer-id", default=None, help="操作対象アカウントID（未指定時は.env）。")
@click.option("--yes", is_flag=True, help="確認をスキップする。")
def create_conversion(
    name: str,
    category: str,
    counting: str,
    value: float | None,
    no_primary: bool,
    customer_id: str | None,
    yes: bool,
) -> None:
    """ウェブサイト用（WEBPAGE）のコンバージョンアクションを作成する。"""
    client = load_client()
    cid = resolve_customer_id(customer_id)

    console.print(
        f"[bold]{name}[/bold] を作成します "
        f"（種別: WEBPAGE / カテゴリ: {category} / カウント: {counting} / "
        f"主要: {'いいえ' if no_primary else 'はい'}）"
    )
    if not yes:
        click.confirm("作成しますか？", abort=True)

    ca_service = client.get_service("ConversionActionService")
    operation = client.get_type("ConversionActionOperation")
    ca = operation.create
    ca.name = name
    ca.type_ = client.enums.ConversionActionTypeEnum.WEBPAGE
    ca.category = client.enums.ConversionActionCategoryEnum[category]
    ca.status = client.enums.ConversionActionStatusEnum.ENABLED
    ca.primary_for_goal = not no_primary
    ca.counting_type = client.enums.ConversionActionCountingTypeEnum[counting]
    if value is not None:
        ca.value_settings.default_value = value
        ca.value_settings.always_use_default_value = True

    response = ca_service.mutate_conversion_actions(
        customer_id=cid, operations=[operation]
    )
    resource_name = response.results[0].resource_name
    conv_id = resource_name.split("/")[-1]
    console.print(
        f"[green]✓ コンバージョンアクションを作成しました。[/green]\n"
        f"[dim]{resource_name}[/dim]\n"
    )
    _print_tag_snippets(client, cid, conv_id)


@conversion.command("update")
@click.option("--id", "conv_id", required=True, help="コンバージョンアクションのID。")
@click.option(
    "--primary/--no-primary",
    "primary",
    default=None,
    help="主要コンバージョン（最適化対象）にする/しない。",
)
@click.option(
    "--status",
    type=click.Choice(["ENABLED", "REMOVED", "HIDDEN"]),
    default=None,
    help="状態を変更する。",
)
@click.option("--customer-id", default=None, help="操作対象アカウントID（未指定時は.env）。")
@click.option("--yes", is_flag=True, help="確認をスキップする。")
def update_conversion(
    conv_id: str,
    primary: bool | None,
    status: str | None,
    customer_id: str | None,
    yes: bool,
) -> None:
    """既存コンバージョンアクションの主要フラグ・状態を変更する。"""
    if primary is None and status is None:
        raise click.ClickException(
            "--primary/--no-primary か --status のいずれかを指定してください。"
        )

    client = load_client()
    cid = resolve_customer_id(customer_id)

    ca_service = client.get_service("ConversionActionService")
    operation = client.get_type("ConversionActionOperation")
    ca = operation.update
    ca.resource_name = ca_service.conversion_action_path(cid, conv_id)
    paths: list[str] = []
    changes: list[str] = []
    if primary is not None:
        ca.primary_for_goal = primary
        paths.append("primary_for_goal")
        changes.append(f"主要={'はい' if primary else 'いいえ'}")
    if status is not None:
        ca.status = client.enums.ConversionActionStatusEnum[status]
        paths.append("status")
        changes.append(f"状態={status}")
    # primary_for_goal=False は proto 既定値のため自動マスク算出だと漏れる。
    # 変更フィールドを明示して FieldMask を組む。
    client.copy_from(operation.update_mask, FieldMask(paths=paths))

    console.print(f"[bold]CV {conv_id}[/bold] を変更します（{', '.join(changes)}）")
    if not yes:
        click.confirm("変更しますか？", abort=True)

    try:
        ca_service.mutate_conversion_actions(customer_id=cid, operations=[operation])
    except GoogleAdsException as ex:
        codes = {e.error_code.mutate_error.name for e in ex.failure.errors}
        if "MUTATE_NOT_ALLOWED" in codes:
            raise click.ClickException(
                f"CV {conv_id} は編集できません（Googleビジネスプロフィール由来の"
                "自動コンバージョン等は API/UI とも直接変更不可）。"
                "主要/副次を切り替えるにはアカウントの「コンバージョン目標」設定を使います。"
            ) from ex
        raise
    console.print("[green]✓ コンバージョンアクションを更新しました。[/green]")


@conversion.command("tag")
@click.option("--id", "conv_id", required=True, help="コンバージョンアクションのID。")
@click.option("--customer-id", default=None, help="操作対象アカウントID（未指定時は.env）。")
def show_tag(conv_id: str, customer_id: str | None) -> None:
    """既存コンバージョンアクションの設置用タグを表示する。"""
    client = load_client()
    cid = resolve_customer_id(customer_id)
    _print_tag_snippets(client, cid, conv_id)


def _print_tag_snippets(client, cid: str, conv_id: str) -> None:
    """tag_snippets（グローバルタグ＋イベントスニペット）を取得して表示する。"""
    query = f"""
        SELECT
          conversion_action.name,
          conversion_action.tag_snippets
        FROM conversion_action
        WHERE conversion_action.id = {conv_id}
    """
    ga_service = client.get_service("GoogleAdsService")
    rows = list(ga_service.search(customer_id=cid, query=query))
    if not rows:
        raise click.ClickException(f"コンバージョンアクション {conv_id} が見つかりません。")

    snippets = rows[0].conversion_action.tag_snippets
    if not snippets:
        console.print(
            "[yellow]タグがまだ生成されていません。"
            "数秒後に `gads conversion tag --id "
            f"{conv_id}` を再実行してください。[/yellow]"
        )
        return

    # WEBPAGE×HTML のスニペットを優先して取り出す。
    snippet = next(
        (s for s in snippets if s.page_format.name == "HTML"),
        snippets[0],
    )
    console.print("[bold cyan]── グローバルタグ（<head> に1回）──[/bold cyan]")
    console.print(snippet.global_site_tag)
    console.print("\n[bold cyan]── イベントスニペット（CV発火時）──[/bold cyan]")
    console.print(snippet.event_snippet)
