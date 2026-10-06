import argparse
import asyncio
from collections import Counter

from bot.config import Settings
from bot.db import make_session_factory
from bot.peers.fetch import (
    fetch_broker_days,
    fetch_member_data,
    fetch_screener_metrics,
    history_dates,
    members,
)
from bot.risk.thresholds import FINANCIAL_SECTOR
from bot.sectors.client import (
    FIXTURES_DIR,
    LIVE_MIN_INTERVAL,
    RecordingTransport,
    SectorsClient,
)
from bot.snapshot.build import take_snapshot


async def record(symbols: list[str], broker_days: int, peers: bool) -> None:
    key = Settings().sectors_api_key.get_secret_value()
    transport = RecordingTransport(FIXTURES_DIR)
    session_factory = make_session_factory("sqlite://")
    seen_subsectors: set[str] = set()
    client = SectorsClient(key, transport=transport, min_interval=LIVE_MIN_INTERVAL)
    async with client:
        for symbol in symbols:
            with session_factory() as session:
                snap, _ = await take_snapshot(client, session, symbol)
            print(f"{snap.symbol} per {snap.as_of} ({snap.sub_sector})", flush=True)
            if peers and snap.sub_sector not in seen_subsectors:
                seen_subsectors.add(snap.sub_sector)
                group = members(snap.sub_sector)
                await fetch_member_data(client, group, snap.as_of)
                await fetch_screener_metrics(
                    client, snap.sub_sector, snap.sector == FINANCIAL_SECTOR, snap.as_of
                )
                print(f"  {len(group)} anggota {snap.sub_sector}", flush=True)
            if broker_days:
                await fetch_broker_days(
                    client, snap.symbol, history_dates(snap, broker_days)
                )
    await transport.aclose()
    kinds = Counter(f.relative_to(FIXTURES_DIR).parts[0] for f in transport.saved)
    print(f"direkam live: {len(transport.saved)} berkas {dict(kinds)}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Lengkapi fixture yang belum ada; setiap berkas baru memakai kredit."
    )
    parser.add_argument("symbols", nargs="+")
    parser.add_argument("--broker-days", type=int, default=0)
    parser.add_argument("--no-peers", action="store_true")
    args = parser.parse_args()
    asyncio.run(record(args.symbols, args.broker_days, not args.no_peers))


if __name__ == "__main__":
    main()
