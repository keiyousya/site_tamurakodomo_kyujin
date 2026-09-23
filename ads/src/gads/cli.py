"""gads コマンドのエントリポイント。"""

from __future__ import annotations

import click

from .commands import ad, budget, campaign, conversion, keyword, report, setup


@click.group()
@click.version_option(package_name="ads", message="gads %(version)s")
def cli() -> None:
    """たむらこどもクリニック 看護師募集の Google 広告運用CLI。"""


cli.add_command(setup.setup)
cli.add_command(report.report)
cli.add_command(budget.budget)
cli.add_command(keyword.keyword)
cli.add_command(conversion.conversion)
cli.add_command(campaign.campaign)
cli.add_command(ad.ad)


if __name__ == "__main__":
    cli()
