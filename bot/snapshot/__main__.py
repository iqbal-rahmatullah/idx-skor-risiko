import argparse
import asyncio

from bot.config import Settings
from bot.db import make_session_factory
from bot.sectors.client import make_client
from bot.snapshot.build import take_snapshot


async def run(symbol: str) -> None:
    settings = Settings()
    session_factory = make_session_factory(settings.database_url)
    async with make_client(settings) as client:
        with session_factory() as session:
            snap, cached = await take_snapshot(client, session, symbol)

    mode = "offline" if settings.sectors_offline else "live"
    known = [s.credits for s in snap.sources if s.credits is not None]
    print(f"{snap.symbol} per {snap.as_of} ({mode})")
    print("data EOD dari cache, peristiwa diperbarui" if cached else "snapshot baru")
    print(
        f"{len(snap.sources)} sumber, kredit tercatat {sum(known)}"
        f" (+{len(snap.sources) - len(known)} tanpa header kredit)"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Bangun dan simpan TickerSnapshot.")
    parser.add_argument("symbol")
    try:
        asyncio.run(run(parser.parse_args().symbol))
    except ValueError as exc:
        raise SystemExit(str(exc)) from None


if __name__ == "__main__":
    main()
