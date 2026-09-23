"""キャンペーン設定コマンド（配信エリア・広告スケジュール・終了日・コンバージョン目標）。

キャンペーンの新規作成は `gads setup`（config.json から一括作成）で行う。
"""

from __future__ import annotations

from datetime import datetime

import click
from google.protobuf import field_mask_pb2
from rich.console import Console
from rich.table import Table

from ..client import load_client, resolve_customer_id

console = Console()

# campaign.end_date_time は日時。終了日「当日いっぱい配信」を表すのに使う。
END_OF_DAY = "23:59:59"


DAYS = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]
MINUTE_NAME = {0: "ZERO", 15: "FIFTEEN", 30: "THIRTY", 45: "FORTY_FIVE"}


@click.group()
def campaign() -> None:
    """配信エリア・広告スケジュール・終了日・コンバージョン目標を設定する。"""


def _read_schedule(client, cid: str, src_campaign_id: str) -> list[dict]:
    """既存キャンペーンの広告スケジュールを読み出す。"""
    ga = client.get_service("GoogleAdsService")
    q = f"""
        SELECT campaign_criterion.ad_schedule.day_of_week,
          campaign_criterion.ad_schedule.start_hour,
          campaign_criterion.ad_schedule.start_minute,
          campaign_criterion.ad_schedule.end_hour,
          campaign_criterion.ad_schedule.end_minute
        FROM campaign_criterion
        WHERE campaign.id = {src_campaign_id}
          AND campaign_criterion.type = AD_SCHEDULE
    """
    out = []
    for r in ga.search(customer_id=cid, query=q):
        s = r.campaign_criterion.ad_schedule
        out.append(
            {
                "day": s.day_of_week.name,
                "sh": s.start_hour,
                "sm": s.start_minute.name,
                "eh": s.end_hour,
                "em": s.end_minute.name,
            }
        )
    return out


@campaign.command("schedule")
@click.option("--campaign-id", required=True, help="設定先のキャンペーンID。")
@click.option(
    "--copy-from",
    default=None,
    help="このキャンペーンIDの広告スケジュールを複製する（既存と同じにする）。",
)
@click.option(
    "--day",
    "days",
    multiple=True,
    type=click.Choice([d[:3] for d in DAYS]),
    help="曜日（MON〜SUN）。--copy-from を使わない場合に複数指定。",
)
@click.option("--start", default=None, help="配信開始時刻 HH:MM（分は00/15/30/45）。")
@click.option("--end", default=None, help="配信終了時刻 HH:MM（分は00/15/30/45）。")
@click.option("--customer-id", default=None, help="操作対象アカウントID（未指定時は.env）。")
@click.option("--yes", is_flag=True, help="確認をスキップする。")
def set_schedule(
    campaign_id: str,
    copy_from: str | None,
    days: tuple[str, ...],
    start: str | None,
    end: str | None,
    customer_id: str | None,
    yes: bool,
) -> None:
    """キャンペーンに広告スケジュール（曜日・時間帯）を設定する。"""
    client = load_client()
    cid = resolve_customer_id(customer_id)

    if copy_from:
        schedule = _read_schedule(client, cid, copy_from)
        if not schedule:
            raise click.ClickException(
                f"キャンペーン {copy_from} に広告スケジュールがありません。"
            )
        source = f"キャンペーン {copy_from} から複製"
    else:
        if not (days and start and end):
            raise click.ClickException(
                "--copy-from を使わない場合は --day（複数可）と --start, --end を指定してください。"
            )
        sh, sm = _parse_hhmm(start)
        eh, em = _parse_hhmm(end)
        full = {d[:3]: d for d in DAYS}
        schedule = [
            {"day": full[d], "sh": sh, "sm": MINUTE_NAME[sm], "eh": eh, "em": MINUTE_NAME[em]}
            for d in days
        ]
        source = f"{start}〜{end} / {', '.join(days)}"

    console.print(
        f"[bold]キャンペーン {campaign_id}[/bold] に広告スケジュールを設定します（{source}）:"
    )
    for s in schedule:
        console.print(
            f"  {s['day']}: {s['sh']:02d}:{s['sm']} - {s['eh']:02d}:{s['em']}"
        )
    if not yes:
        click.confirm("設定しますか？", abort=True)

    campaign_service = client.get_service("CampaignService")
    crit_service = client.get_service("CampaignCriterionService")
    ops = []
    for s in schedule:
        op = client.get_type("CampaignCriterionOperation")
        cc = op.create
        cc.campaign = campaign_service.campaign_path(cid, campaign_id)
        cc.ad_schedule.day_of_week = client.enums.DayOfWeekEnum[s["day"]]
        cc.ad_schedule.start_hour = s["sh"]
        cc.ad_schedule.start_minute = client.enums.MinuteOfHourEnum[s["sm"]]
        cc.ad_schedule.end_hour = s["eh"]
        cc.ad_schedule.end_minute = client.enums.MinuteOfHourEnum[s["em"]]
        ops.append(op)

    crit_service.mutate_campaign_criteria(customer_id=cid, operations=ops)
    console.print(f"[green]✓ 広告スケジュールを{len(ops)}件設定しました。[/green]")


def _parse_hhmm(s: str) -> tuple[int, int]:
    """HH:MM をパースする。分は 00/15/30/45 のみ。"""
    try:
        h, m = s.split(":")
        h, m = int(h), int(m)
    except ValueError as e:
        raise click.ClickException(f"時刻の形式が不正です: {s}（HH:MM）") from e
    if m not in MINUTE_NAME:
        raise click.ClickException("分は 00/15/30/45 のみ指定できます。")
    return h, m


@campaign.command("end-date")
@click.option("--campaign-id", required=True, help="対象キャンペーンID。")
@click.option(
    "--date",
    "end_date",
    default=None,
    help="配信終了日 YYYY-MM-DD（この日までは配信し、翌日から停止する）。",
)
@click.option("--clear", is_flag=True, help="終了日を解除し、無期限配信に戻す。")
@click.option("--customer-id", default=None, help="操作対象アカウントID（未指定時は.env）。")
@click.option("--yes", is_flag=True, help="確認をスキップする。")
def set_end_date(
    campaign_id: str,
    end_date: str | None,
    clear: bool,
    customer_id: str | None,
    yes: bool,
) -> None:
    """キャンペーンの配信終了日を設定・解除する。

    募集締切・休診期間の配信停止に使う。終了日の翌日から自動的に配信が止まるため、
    当日にPAUSED操作をしなくてよい。再開時は --clear で解除する。
    """
    if bool(end_date) == clear:
        raise click.ClickException("--date と --clear はどちらか一方を指定してください。")

    if end_date:
        try:
            datetime.strptime(end_date, "%Y-%m-%d")
        except ValueError as e:
            raise click.ClickException(
                f"日付の形式が不正です: {end_date}（YYYY-MM-DD）"
            ) from e
        # 指定日の終業時刻まで配信させるため、その日の23:59:59を終了日時とする。
        new_value = f"{end_date} {END_OF_DAY}"
    else:
        new_value = ""

    client = load_client()
    cid = resolve_customer_id(customer_id)

    ga_service = client.get_service("GoogleAdsService")
    query = f"""
        SELECT campaign.name, campaign.status, campaign.end_date_time
        FROM campaign
        WHERE campaign.id = {campaign_id}
    """
    result = list(ga_service.search(customer_id=cid, query=query))
    if not result:
        raise click.ClickException(f"キャンペーン {campaign_id} が見つかりません。")

    row = result[0]
    current_label = row.campaign.end_date_time or "なし（無期限）"
    new_label = new_value or "なし（無期限）"

    console.print(
        f"[bold]{row.campaign.name}[/bold]（{row.campaign.status.name}）の配信終了日時: "
        f"{current_label} → [green]{new_label}[/green]"
    )
    if end_date:
        console.print(f"[dim]※ {end_date} までは配信し、翌日から停止します。[/dim]")
    if not yes:
        click.confirm("変更しますか？", abort=True)

    campaign_service = client.get_service("CampaignService")
    operation = client.get_type("CampaignOperation")
    c = operation.update
    c.resource_name = campaign_service.campaign_path(cid, campaign_id)
    if new_value:
        c.end_date_time = new_value
    # 解除は「空値 + update_mask に載せる」で行う。空文字は protobuf_helpers.field_mask が
    # 差分と見なさず落としてしまうため、マスクは常に明示的に組む。
    client.copy_from(
        operation.update_mask, field_mask_pb2.FieldMask(paths=["end_date_time"])
    )
    campaign_service.mutate_campaigns(customer_id=cid, operations=[operation])
    console.print(f"[green]✓ 配信終了日時を {new_label} にしました。[/green]")


# --- 配信エリア -----------------------------------------------------------------

# クリニックの所在地（前橋市西片貝町3丁目。国土地理院の住所検索で取得）
CLINIC_LAT = 36.387417
CLINIC_LNG = 139.098389


@campaign.command("radius")
@click.option("--campaign-id", required=True, help="対象キャンペーンID。")
@click.option("--km", "radius_km", required=True, type=float, help="配信半径（km）。")
@click.option("--lat", type=float, default=CLINIC_LAT, show_default=True, help="中心の緯度。")
@click.option("--lng", type=float, default=CLINIC_LNG, show_default=True, help="中心の経度。")
@click.option("--customer-id", default=None, help="操作対象アカウントID（未指定時は.env）。")
@click.option("--yes", is_flag=True, help="確認をスキップする。")
def set_radius(
    campaign_id: str,
    radius_km: float,
    lat: float,
    lng: float,
    customer_id: str | None,
    yes: bool,
) -> None:
    """配信エリアを「中心から半径◯km」に置き換える。

    既存の地域・半径ターゲティング（除外以外）はすべて削除してから追加する。
    """
    client = load_client()
    cid = resolve_customer_id(customer_id)
    ga_service = client.get_service("GoogleAdsService")

    query = f"""
        SELECT campaign_criterion.resource_name,
               campaign_criterion.type,
               campaign_criterion.location.geo_target_constant,
               campaign_criterion.proximity.radius
        FROM campaign_criterion
        WHERE campaign.id = {campaign_id}
          AND campaign_criterion.type IN (LOCATION, PROXIMITY)
          AND campaign_criterion.negative = FALSE
    """
    current = list(ga_service.search(customer_id=cid, query=query))

    console.print(f"[bold]キャンペーン {campaign_id}[/bold] の配信エリア:")
    for r in current:
        cc = r.campaign_criterion
        label = (
            cc.location.geo_target_constant
            if cc.type_.name == "LOCATION"
            else f"半径 {cc.proximity.radius}km"
        )
        console.print(f"  [red]- {label}[/red]")
    console.print(f"  [green]+ 半径 {radius_km:g}km（{lat}, {lng}）[/green]")
    if not yes:
        click.confirm("変更しますか？", abort=True)

    crit_service = client.get_service("CampaignCriterionService")
    campaign_service = client.get_service("CampaignService")
    ops = []
    for r in current:
        op = client.get_type("CampaignCriterionOperation")
        op.remove = r.campaign_criterion.resource_name
        ops.append(op)
    op = client.get_type("CampaignCriterionOperation")
    cc = op.create
    cc.campaign = campaign_service.campaign_path(cid, campaign_id)
    cc.proximity.geo_point.latitude_in_micro_degrees = int(round(lat * 1_000_000))
    cc.proximity.geo_point.longitude_in_micro_degrees = int(round(lng * 1_000_000))
    cc.proximity.radius = radius_km
    cc.proximity.radius_units = client.enums.ProximityRadiusUnitsEnum.KILOMETERS
    ops.append(op)

    # 削除と追加を1リクエストにして、エリア未設定（＝全国配信）の瞬間を作らない
    crit_service.mutate_campaign_criteria(customer_id=cid, operations=ops)
    console.print(f"[green]✓ 配信エリアを半径 {radius_km:g}km に変更しました。[/green]")


# --- コンバージョン目標 -------------------------------------------------------
#
# コンバージョン目標には「アカウント既定（customer_conversion_goal）」と
# 「キャンペーン個別（campaign_conversion_goal）」の2層がある。キャンペーン個別が
# 設定されているとアカウント既定より優先され、biddable=False の目標は
# conversions 列に計上されず、入札の最適化対象からも外れる（計測は all_conversions
# に残るので「CV0なのにクリックはある」という見え方になる）。
#
# 目標は (category, origin) の組で識別する。resource_name は
# campaignConversionGoals/{campaign_id}~{category}~{origin}。


def _goal_key(row_goal) -> tuple[str, str]:
    return (row_goal.category.name, row_goal.origin.name)


def _fetch_account_goals(ga_service, cid: str) -> dict[tuple[str, str], bool]:
    """アカウント既定のコンバージョン目標を {(category, origin): biddable} で返す。"""
    query = """
        SELECT
          customer_conversion_goal.category,
          customer_conversion_goal.origin,
          customer_conversion_goal.biddable
        FROM customer_conversion_goal
    """
    return {
        _goal_key(row.customer_conversion_goal): row.customer_conversion_goal.biddable
        for row in ga_service.search(customer_id=cid, query=query)
    }


def _fetch_campaign_goals(ga_service, cid: str, campaign_id: int | None):
    """キャンペーン個別の目標を返す。campaign_id 未指定なら全キャンペーン分。"""
    where = f"WHERE campaign.id = {campaign_id}" if campaign_id else ""
    query = f"""
        SELECT
          campaign.id,
          campaign.name,
          campaign_conversion_goal.category,
          campaign_conversion_goal.origin,
          campaign_conversion_goal.biddable
        FROM campaign_conversion_goal
        {where}
    """
    return list(ga_service.search(customer_id=cid, query=query))


def _fetch_action_labels(ga_service, cid: str) -> dict[tuple[str, str], list[str]]:
    """(category, origin) → コンバージョンアクション名。表示を人間が読める形にするだけ。"""
    query = """
        SELECT
          conversion_action.name,
          conversion_action.category,
          conversion_action.origin
        FROM conversion_action
        WHERE conversion_action.status = 'ENABLED'
    """
    labels: dict[tuple[str, str], list[str]] = {}
    for row in ga_service.search(customer_id=cid, query=query):
        key = (row.conversion_action.category.name, row.conversion_action.origin.name)
        labels.setdefault(key, []).append(row.conversion_action.name)
    return labels


def _mark(biddable: bool) -> str:
    return "[green]主要[/green]" if biddable else "[dim]副次[/dim]"


@campaign.command("goals")
@click.option("--campaign-id", type=int, help="対象キャンペーンID（未指定なら全件）。")
@click.option("--customer-id", help="操作対象アカウントID（未指定時は.env）。")
def goals(campaign_id: int | None, customer_id: str | None) -> None:
    """コンバージョン目標をアカウント既定と比較して表示する。

    「主要」だけが conversions 列に計上され、入札の最適化対象になる。
    アカウント既定と食い違う行には差分マークが付く。
    """
    client = load_client()
    cid = resolve_customer_id(customer_id)
    ga_service = client.get_service("GoogleAdsService")

    account = _fetch_account_goals(ga_service, cid)
    labels = _fetch_action_labels(ga_service, cid)
    rows = _fetch_campaign_goals(ga_service, cid, campaign_id)
    if not rows:
        raise click.ClickException("コンバージョン目標が取得できませんでした。")

    by_campaign: dict[str, list] = {}
    for row in rows:
        by_campaign.setdefault(f"{row.campaign.name}（{row.campaign.id}）", []).append(row)

    total_diff = 0
    for title, campaign_rows in by_campaign.items():
        table = Table(title=title, title_justify="left")
        table.add_column("目標（カテゴリ / 発生元）")
        table.add_column("コンバージョンアクション")
        table.add_column("アカウント既定")
        table.add_column("このキャンペーン")
        table.add_column("差分")

        for row in sorted(campaign_rows, key=lambda r: r.campaign_conversion_goal.category.name):
            goal = row.campaign_conversion_goal
            key = _goal_key(goal)
            default = account.get(key)
            differs = default is not None and default != goal.biddable
            total_diff += 1 if differs else 0
            table.add_row(
                f"{key[0]} / {key[1]}",
                "、".join(labels.get(key, [])) or "[dim]—[/dim]",
                "[dim]—[/dim]" if default is None else _mark(default),
                _mark(goal.biddable),
                "[red]![/red]" if differs else "",
            )
        console.print(table)

    if total_diff:
        console.print(
            f"[yellow]アカウント既定と異なる目標が {total_diff} 件あります。"
            "揃えるには gads campaign sync-goals --campaign-id … [/yellow]"
        )
    else:
        console.print("[green]すべてアカウント既定と一致しています。[/green]")


@campaign.command("sync-goals")
@click.option("--campaign-id", required=True, type=int, help="対象キャンペーンID。")
@click.option("--customer-id", help="操作対象アカウントID（未指定時は.env）。")
@click.option("--yes", is_flag=True, help="確認プロンプトを省略する。")
def sync_goals(campaign_id: int, customer_id: str | None, yes: bool) -> None:
    """キャンペーン個別のコンバージョン目標をアカウント既定に揃える。

    キャンペーンごとに目標がずれていると、同じアカウントなのに計上されるCVの
    種類が変わってしまい、キャンペーン間の比較ができなくなる。入札戦略が
    「コンバージョン数の最大化」の場合は最適化の向き先そのものがずれる。
    """
    client = load_client()
    cid = resolve_customer_id(customer_id)
    ga_service = client.get_service("GoogleAdsService")

    account = _fetch_account_goals(ga_service, cid)
    labels = _fetch_action_labels(ga_service, cid)
    rows = _fetch_campaign_goals(ga_service, cid, campaign_id)
    if not rows:
        raise click.ClickException(f"キャンペーン {campaign_id} が見つかりません。")

    campaign_name = rows[0].campaign.name
    changes = []
    for row in rows:
        goal = row.campaign_conversion_goal
        key = _goal_key(goal)
        default = account.get(key)
        if default is not None and default != goal.biddable:
            changes.append((key, goal.biddable, default))

    if not changes:
        console.print(
            f"[green]✓ {campaign_name} の目標はすでにアカウント既定と一致しています。[/green]"
        )
        return

    console.print(f"[bold]{campaign_name}（{campaign_id}）[/bold] の変更内容:")
    for key, before, after in changes:
        name = "、".join(labels.get(key, [])) or f"{key[0]} / {key[1]}"
        console.print(f"  {name}: {_mark(before)} → {_mark(after)}")
    if not yes:
        click.confirm("変更しますか？", abort=True)

    goal_service = client.get_service("CampaignConversionGoalService")
    operations = []
    for key, _before, after in changes:
        operation = client.get_type("CampaignConversionGoalOperation")
        g = operation.update
        g.resource_name = goal_service.campaign_conversion_goal_path(
            cid, campaign_id, key[0], key[1]
        )
        g.biddable = after
        # biddable は False にも倒すため、差分検出まかせにせずマスクを明示する。
        client.copy_from(
            operation.update_mask, field_mask_pb2.FieldMask(paths=["biddable"])
        )
        operations.append(operation)

    goal_service.mutate_campaign_conversion_goals(customer_id=cid, operations=operations)
    console.print(f"[green]✓ {len(changes)} 件の目標をアカウント既定に揃えました。[/green]")
