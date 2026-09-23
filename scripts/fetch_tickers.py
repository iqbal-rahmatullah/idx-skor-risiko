import json
from pathlib import Path

import certifi
import httpx

from bot.config import Settings

OUT = Path(__file__).resolve().parent.parent / "bot" / "data" / "tickers.json"

def main() -> None:
    key = Settings().sectors_api_key.get_secret_value()
    params = {
        "where": "sub_sector != '' and listing_board != ''",
        "include_query_values": "true",
        "limit": 200,
        "offset": 0,
    }
    tickers = {}
    with httpx.Client(
        base_url="https://api.sectors.app/v2",
        headers={"Authorization": key},
        verify=certifi.where(),
        timeout=60,
    ) as client:
        while params["offset"] is not None:
            resp = client.get("/companies/", params=params)
            resp.raise_for_status()
            body = resp.json()
            for row in body["results"]:
                tickers[row["symbol"].removesuffix(".JK")] = {
                    "name": row["company_name"],
                    "sub_sector": row["query_values"]["sub_sector"],
                    "listing_board": row["query_values"]["listing_board"],
                }
            params["offset"] = body["pagination"]["next_offset"]

    if len(tickers) != body["pagination"]["total_count"]:
        raise SystemExit(
            f"Jumlah tidak cocok: {len(tickers)} vs {body['pagination']['total_count']}"
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(tickers, indent=1, ensure_ascii=False, sort_keys=True) + "\n"
    )
    print(f"{len(tickers)} emiten → {OUT}")


if __name__ == "__main__":
    main()
