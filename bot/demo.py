import argparse
import asyncio
import html
import json
import re
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from telegram import Bot

from bot.config import Settings
from bot.db import make_session_factory, set_last_round, upsert_registration
from bot.jobs.rounds import daily_round
from bot.sectors.client import FIXTURES_DIR, SectorsClient, fixture_transport
from bot.telegram.services import Deps, assess, send_card

LABEL = "SKENARIO DEMO"
DAY2 = date(2026, 9, 23)
JAKARTA = ZoneInfo("Asia/Jakarta")
SCENARIO: dict[str, dict[str, Any]] = {
    "CASH": {"close": 262, "volume": 20_000_000},
    "BBRI": {
        "close": 3500,
        "volume": 1_200_000_000,
        "actions": {
            "upcoming_dividend": [{"ex_date": DAY2.isoformat(), "dividend_amount": 150}]
        },
    },
}


def read(out: Path, rel: str) -> Any:
    file = out / f"{rel}.json"
    return json.loads(
        (file if file.exists() else FIXTURES_DIR / f"{rel}.json").read_text()
    )


def write(out: Path, rel: str, body: Any) -> None:
    file = out / f"{rel}.json"
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n")


def next_day_overlay(
    out: Path,
    symbol: str,
    day: date,
    *,
    close: float | None = None,
    volume: int | None = None,
    news: list[dict[str, Any]] | None = None,
    actions: dict[str, list[dict[str, Any]]] | None = None,
) -> None:
    daily = read(out, f"daily/{symbol}")
    last = max(
        (r for r in daily if r["date"] < day.isoformat()), key=lambda r: r["date"]
    )
    close = last["close"] if close is None else close
    volume = last["volume"] if volume is None else volume
    low, high = sorted((close, last["close"]))
    bar = {**last, "date": day.isoformat(), "open": last["close"], "high": high}
    bar |= {"low": low, "close": close, "volume": volume}
    write(
        out, f"daily/{symbol}", [r for r in daily if r["date"] != bar["date"]] + [bar]
    )

    report = read(out, f"company/report/{symbol}")
    report["overview"] |= {
        "latest_close_date": day.isoformat(),
        "last_close_price": close,
        "daily_close_change": close / last["close"] - 1,
    }
    write(out, f"company/report/{symbol}", report)

    broker = read(out, f"broker-summary/{symbol}/top/{last['date']}")
    write(
        out,
        f"broker-summary/{symbol}/top/{day.isoformat()}",
        broker | {"start": day.isoformat(), "end": day.isoformat()},
    )
    if news:
        body = read(out, f"news/{symbol}")
        body["results"] += [
            {
                "source": f"demo:{n['title']}",
                "tags": [],
                **n,
                "symbols": [f"{symbol}.JK"],
            }
            for n in news
        ]
        write(out, f"news/{symbol}", body)
    if actions:
        body = read(out, f"company/corporate-actions/{symbol}")
        for kind, rows in actions.items():
            body["corporate_actions"][kind] = (
                body["corporate_actions"].get(kind) or []
            ) + rows
        write(out, f"company/corporate-actions/{symbol}", body)


class Collector:
    def __init__(self) -> None:
        self.texts: list[str] = []

    async def send_message(self, *, text: str, **_: Any) -> None:
        self.texts.append(text)


def plain(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text))


async def play() -> list[str]:
    with tempfile.TemporaryDirectory() as tmp:
        overlay = Path(tmp)
        for symbol, change in SCENARIO.items():
            next_day_overlay(overlay, symbol, DAY2, **change)
        session_factory = make_session_factory("sqlite://")

        def deps(*overlays: Path) -> Deps:
            return Deps(
                session_factory=session_factory,
                make_client=lambda: SectorsClient(
                    "demo", transport=fixture_transport(FIXTURES_DIR, *overlays)
                ),
                fill_gaps=True,
            )

        with session_factory() as session:
            for symbol in SCENARIO:
                upsert_registration(
                    session, user_id=0, chat_id=0, symbol=symbol, thread_id=None
                )
            set_last_round(
                session, 0, datetime(2026, 9, 23, 6, tzinfo=JAKARTA).astimezone(UTC)
            )
        for symbol in SCENARIO:
            await assess(deps(), symbol)
        collector = Collector()
        await daily_round(
            collector,
            deps(overlay),
            datetime(2026, 9, 24, 6, tzinfo=JAKARTA).astimezone(UTC),
            title_note=f"{LABEL} · 🔔 Kabar pemantauan",
        )
    return collector.texts


async def send(texts: list[str], chat_id: int, thread_id: int | None) -> None:
    async with Bot(Settings().telegram_bot_token.get_secret_value()) as bot:
        for text in texts:
            await send_card(bot, chat_id, [text], thread_id)


def main() -> None:
    parser = argparse.ArgumentParser(description=f"Putar {LABEL} dua momen, offline.")
    parser.add_argument("--chat", type=int, help="kirim juga ke chat Telegram ini")
    parser.add_argument("--thread", type=int, help="topik tujuan di chat itu")
    args = parser.parse_args()
    texts = asyncio.run(play())
    print("\n\n────────\n\n".join(plain(t) for t in texts))
    if args.chat is not None:
        asyncio.run(send(texts, args.chat, args.thread))


if __name__ == "__main__":
    main()
