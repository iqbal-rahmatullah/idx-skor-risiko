import argparse
import asyncio

from bot.config import Settings
from bot.db import make_session_factory
from bot.sectors.client import FIXTURES_DIR, RecordingTransport, SectorsClient
from bot.snapshot.build import take_snapshot


async def record(symbols: list[str]) -> None:
    key = Settings().sectors_api_key.get_secret_value()
    transport = RecordingTransport(FIXTURES_DIR)
    session_factory = make_session_factory("sqlite://")
    async with SectorsClient(key, transport=transport) as client:
        for symbol in symbols:
            with session_factory() as session:
                snap, _ = await take_snapshot(client, session, symbol)
            credits = sum(s.credits or 0 for s in snap.sources)
            print(f"{snap.symbol} per {snap.as_of}: kredit tercatat {credits}")
    await transport.aclose()
    for file in transport.saved:
        print(f"direkam: {file.relative_to(FIXTURES_DIR)}")
    if not transport.saved:
        print("semua fixture sudah ada, tidak ada panggilan live")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Lengkapi fixture yang belum ada dengan satu panggilan live per endpoint."
    )
    parser.add_argument("symbols", nargs="+")
    asyncio.run(record(parser.parse_args().symbols))


if __name__ == "__main__":
    main()
