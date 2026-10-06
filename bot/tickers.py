import difflib
import json
from pathlib import Path

TICKERS: dict[str, dict[str, str]] = json.loads(
    (Path(__file__).parent / "data" / "tickers.json").read_text()
)


def strip_jk(symbol: str) -> str:
    return symbol.removesuffix(".JK")


def valid_ticker(text: str) -> str | None:
    symbol = text.strip().upper().removesuffix(".JK")
    return symbol if symbol in TICKERS else None


def suggest_tickers(text: str, n: int = 3) -> list[str]:
    query = text.strip()
    close = difflib.get_close_matches(
        query.upper().removesuffix(".JK"), TICKERS, n=n, cutoff=0.6
    )
    by_name = [
        s
        for s, v in TICKERS.items()
        if len(query) >= 4 and query.lower() in v["name"].lower()
    ]
    return list(dict.fromkeys(close + by_name))[:n]
