"""レポート取得コマンド（GAQL → 表示 / CSV）。"""

from __future__ import annotations

import csv
import sys

import click
from rich.console import Console
from rich.table import Table

from ..client import load_client, resolve_customer_id

console = Console()

# 表示用の列見出しの差し替え（実値は _format_field で整形済み）。
HEADER_LABELS: dict[str, str] = {
    "cost_micros": "費用(円)",
}

# よく使うレポートのプリセット（GAQL）。--query で任意のGAQLを直接渡すことも可能。
PRESETS: dict[str, str] = {
    "campaign": """
        SELECT
          campaign.id,
          campaign.name,
          campaign.status,
          metrics.cost_micros,
          metrics.impressions,
          metrics.clicks,
          metrics.conversions
        FROM campaign
        WHERE segments.date DURING {date_range}
        ORDER BY metrics.cost_micros DESC
    """,
    "ad_group": """
        SELECT
          campaign.name,
          ad_group.id,
          ad_group.name,
          ad_group.status,
          metrics.cost_micros,
          metrics.clicks,
          metrics.conversions
        FROM ad_group
        WHERE segments.date DURING {date_range}
        ORDER BY metrics.cost_micros DESC
    """,
    "keyword": """
        SELECT
          campaign.name,
          ad_group.name,
          ad_group_criterion.keyword.text,
          ad_group_criterion.keyword.match_type,
          metrics.cost_micros,
          metrics.clicks,
          metrics.conversions
        FROM keyword_view
        WHERE segments.date DURING {date_range}
        ORDER BY metrics.cost_micros DESC
    """,
}


@click.command()
@click.option(
    "--preset",
    type=click.Choice(list(PRESETS.keys())),
    default="campaign",
    show_default=True,
    help="プリセットGAQL。--query 指定時は無視される。",
)
@click.option("--query", default=None, help="任意のGAQLを直接指定する。")
@click.option(
    "--date-range",
    default="LAST_30_DAYS",
    show_default=True,
    help="プリセットの集計期間（例: LAST_7_DAYS, LAST_30_DAYS, THIS_MONTH）。",
)
@click.option("--customer-id", default=None, help="操作対象アカウントID（未指定時は.env）。")
@click.option(
    "--csv",
    "csv_out",
    is_flag=True,
    help="表ではなくCSVを標準出力へ書き出す（リダイレクトで保存）。",
)
@click.option("--limit", type=int, default=None, help="表示行数の上限。")
def report(
    preset: str,
    query: str | None,
    date_range: str,
    customer_id: str | None,
    csv_out: bool,
    limit: int | None,
) -> None:
    """成果レポートを取得する（GAQL）。"""
    client = load_client()
    cid = resolve_customer_id(customer_id)
    gaql = query or PRESETS[preset].format(date_range=date_range)
    if limit:
        gaql = gaql.strip() + f"\nLIMIT {limit}"

    ga_service = client.get_service("GoogleAdsService")
    stream = ga_service.search_stream(customer_id=cid, query=gaql)

    headers: list[str] = []
    rows: list[list[str]] = []
    for batch in stream:
        if not headers:
            headers = [
                HEADER_LABELS.get(name, name)
                for name in (f.split(".")[-1] for f in batch.field_mask.paths)
            ]
        for row in batch.results:
            rows.append([_format_field(row, path) for path in batch.field_mask.paths])

    if not rows:
        console.print("[yellow]該当データがありませんでした。[/yellow]")
        return

    if csv_out:
        writer = csv.writer(sys.stdout)
        writer.writerow(headers)
        writer.writerows(rows)
        return

    table = Table(show_header=True, header_style="bold cyan")
    for h in headers:
        table.add_column(h)
    for r in rows:
        table.add_row(*r)
    console.print(table)
    console.print(f"[dim]{len(rows)} 行[/dim]")


def _format_field(row, path: str) -> str:
    """ドット区切りのフィールドパスから値を取り出して整形する。"""
    obj = row
    for part in path.split("."):
        obj = getattr(obj, part)
    # 費用は micros（100万分の1通貨単位）なので円に直す
    if path.endswith("cost_micros"):
        return f"{int(obj) / 1_000_000:,.0f}"
    return str(obj)
