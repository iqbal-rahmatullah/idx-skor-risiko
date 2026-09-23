import json
from pathlib import Path

TICKERS: dict[str, dict[str, str]] = json.loads(
    (Path(__file__).parent / "data" / "tickers.json").read_text()
)


def valid_ticker(text: str) -> str | None:
    symbol = text.strip().upper().removesuffix(".JK")
    return symbol if symbol in TICKERS else None
