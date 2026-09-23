import argparse
import asyncio

from bot.config import Settings
from bot.db import make_session_factory
from bot.risk.build_json import build_indicators, dumps
from bot.sectors.client import make_client
from bot.snapshot.build import take_snapshot


async def run(symbol: str) -> str:
    settings = Settings()
    session_factory = make_session_factory(settings.database_url)
    async with make_client(settings) as client:
        with session_factory() as session:
            snap, _ = await take_snapshot(client, session, symbol)
    return dumps(build_indicators(snap))


def main() -> None:
    parser = argparse.ArgumentParser(description="Cetak indicators.json satu saham.")
    parser.add_argument("symbol")
    try:
        print(asyncio.run(run(parser.parse_args().symbol)), end="")
    except ValueError as exc:
        raise SystemExit(str(exc)) from None


if __name__ == "__main__":
    main()
