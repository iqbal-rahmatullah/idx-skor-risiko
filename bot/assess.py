from sqlalchemy.orm import Session

from bot.db import broker_history, save_broker_day, save_snapshot
from bot.peers.fetch import fetch_broker_days, history_dates
from bot.peers.stats import refresh_peer_stats
from bot.risk.thresholds import BROKER_MIN_HISTORY, FINANCIAL_SECTOR
from bot.sectors.client import SectorsClient
from bot.snapshot.build import attach_context, take_snapshot
from bot.snapshot.models import TickerSnapshot


async def backfill_broker(
    client: SectorsClient, session: Session, snap: TickerSnapshot, days: int
) -> None:
    known = {b.date for b in broker_history(session, snap.symbol, snap.as_of)}
    missing = [d for d in history_dates(snap, days) if d not in known]
    for day, body in (await fetch_broker_days(client, snap.symbol, missing)).items():
        # Hari tanpa data tetap disimpan supaya tidak diambil ulang dengan kredit.
        save_broker_day(
            session,
            snap.symbol,
            day,
            body or {"end": day.isoformat(), "top_buyers": [], "top_sellers": []},
        )


async def prepare(
    client: SectorsClient,
    session: Session,
    symbol: str,
    *,
    fill_peers: bool,
    fill_broker: bool,
) -> TickerSnapshot:
    snap, _ = await take_snapshot(client, session, symbol)
    changed = False
    if fill_peers and snap.peers is None:
        await refresh_peer_stats(
            client,
            session,
            snap.sub_sector,
            snap.sector == FINANCIAL_SECTOR,
            snap.as_of,
        )
        changed = True
    if fill_broker and len(snap.broker_history) < BROKER_MIN_HISTORY:
        await backfill_broker(client, session, snap, BROKER_MIN_HISTORY)
        changed = True
    if changed:
        snap = attach_context(session, snap)
        save_snapshot(session, snap)
    return snap
