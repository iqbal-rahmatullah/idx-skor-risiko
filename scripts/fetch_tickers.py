import asyncio
import json
from pathlib import Path

from bot.config import Settings
from bot.sectors.client import SectorsClient

OUT = Path(__file__).resolve().parent.parent / "bot" / "data" / "tickers.json"


async def fetch() -> dict[str, dict[str, str]]:
    key = Settings().sectors_api_key.get_secret_value()
    async with SectorsClient(key) as client:
        rows = await client.get_all_pages(
            "/companies/",
            where="sub_sector != '' and listing_board != ''",
            include_query_values="true",
            limit=200,
        )
    return {
        row["symbol"].removesuffix(".JK"): {
            "name": row["company_name"],
            "sub_sector": row["query_values"]["sub_sector"],
            "listing_board": row["query_values"]["listing_board"],
        }
        for row in rows
    }


def main() -> None:
    tickers = asyncio.run(fetch())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(tickers, indent=1, ensure_ascii=False, sort_keys=True) + "\n"
    )
    print(f"{len(tickers)} emiten → {OUT}")


if __name__ == "__main__":
    main()
