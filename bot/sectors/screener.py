import re

from bot.sectors.client import SectorsClient
from bot.tickers import strip_jk

DAILY_CHANGE = "daily_close_change"


def slug(sub_sector: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", sub_sector.lower().replace("&", "")).strip("-")


async def fetch_screener_metric(
    client: SectorsClient, sub_sector: str, expression: str
) -> dict[str, float | None]:
    rows = await client.get_all_pages(
        "/companies/",
        missing_ok=True,
        where=f"sub_sector = '{slug(sub_sector)}'",
        order_by=f"-{expression}",
        include_query_values="true",
        limit=200,
    )
    return {
        strip_jk(r["symbol"]): (r.get("query_values") or {}).get(expression)
        for r in rows
    }
