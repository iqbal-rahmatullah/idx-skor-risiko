import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, time, timedelta
from itertools import groupby
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy.orm import Session
from telegram import Bot
from telegram.ext import Application, ContextTypes, Job

from bot.assess import prepare
from bot.db import (
    Registration,
    active_registrations,
    alerted_keys,
    get_last_round,
    last_eod,
    latest_risk_docs,
    latest_snapshot,
    mark_alerted,
    mark_eod,
    save_risk_doc,
    set_last_round,
)
from bot.idx.refresh import refresh_notations
from bot.narrate.gate import Checked
from bot.peers.stats import refresh_peer_stats
from bot.risk.build_json import build_indicators
from bot.risk.compare import alert_reasons, annotate, trigger_keys
from bot.risk.format import day
from bot.risk.thresholds import FINANCIAL_SECTOR
from bot.snapshot.models import TickerSnapshot
from bot.telegram.render_fallback import LIMIT, clip, render_alert, visible_len
from bot.telegram.services import FETCH_ERRORS, Deps, send_card

log = logging.getLogger(__name__)

JAKARTA = ZoneInfo("Asia/Jakarta")
DAILY_AT = time(6, 0, tzinfo=JAKARTA)
WEEKLY_AT = time(5, 0, tzinfo=JAKARTA)
# JobQueue memakai 0 = Minggu, jadi Senin–Jumat = 1–5.
WEEKDAYS = (1, 2, 3, 4, 5)
MONDAY = (1,)
EVENT_LOOKBACK = timedelta(days=1)
TITLE = "🔔 Kabar pemantauan"


def event_candidates(
    snap: TickerSnapshot, summaries: dict[str, str]
) -> list[tuple[date, str, str]]:
    events = []
    for article in snap.events.news:
        when = date.fromisoformat(article["timestamp"][:10])
        key = f"news:{article.get('source') or article['title']}"
        text = summaries.get(article.get("source") or "") or clip(article["title"])
        events.append((when, key, f"Berita {day(when)}: {text}"))
    for filing in snap.ownership.insider_filings:
        when = date.fromisoformat(filing["timestamp"][:10])
        holder = filing.get("holder_name") or "Orang dalam"
        verb = {"buy": "membeli", "sell": "menjual"}.get(
            filing.get("transaction_type"), "melaporkan transaksi"
        )
        key = f"filing:{filing.get('source')}:{filing['timestamp']}:{holder}"
        events.append((when, key, f"{holder} {verb} saham ({day(when)})"))
    for halt in snap.events.suspensions:
        when = date.fromisoformat(halt["suspension_date"][:10])
        key = f"suspension:{halt['suspension_date']}:{halt.get('pdf_url') or halt.get('reason')}"
        events.append((when, key, f"Suspensi mulai {day(when)}"))
    return events


def new_events(
    snap: TickerSnapshot,
    since: datetime,
    seen: set[str],
    summaries: dict[str, str] | None = None,
) -> tuple[list[str], list[str]]:
    start = since.astimezone(JAKARTA).date() - EVENT_LOOKBACK
    fresh = [
        (key, text)
        for when, key, text in event_candidates(snap, summaries or {})
        if when >= start and key not in seen
    ]
    return [text for _, text in fresh], [key for key, _ in fresh]


def news_summaries(doc: dict[str, Any], checked: Checked) -> dict[str, str]:
    return {
        item["source"]: checked.news[item["id"]]
        for item in doc["context"]["negative_news"]
        if item["id"] in checked.news and item.get("source")
    }


async def deliver(
    bot: Bot,
    session: Session,
    reg: Registration,
    scored: tuple[dict[str, Any], dict[str, Any] | None],
    snap: TickerSnapshot,
    since: datetime,
    narration: Callable[[str], Awaitable[Checked | None]],
    title_note: str,
) -> bool:
    doc, previous = scored
    seen = alerted_keys(session, reg.user_id, reg.symbol)
    triggers = trigger_keys(doc, previous)
    quiet = triggers <= seen
    if not alert_reasons(doc, previous, new_events(snap, since, seen)[0], quiet=quiet):
        return False

    def compose(checked: Checked | None) -> tuple[str, list[str]]:
        summaries = news_summaries(doc, checked) if checked else None
        events, keys = new_events(snap, since, seen, summaries)
        explanations = checked.explanations if checked else None
        text = render_alert(
            doc,
            previous_score=previous["score"]["value"] if previous else None,
            reasons=alert_reasons(doc, previous, events, explanations, quiet=quiet),
            title_note=title_note,
            summary=checked.summary if checked else None,
            explanations=explanations,
        )
        return text, keys

    checked = await narration(reg.symbol)
    text, keys = compose(checked)
    if checked is not None and visible_len(text) > LIMIT:
        text, keys = compose(None)
    await send_card(bot, reg.chat_id, [text], reg.thread_id)
    mark_alerted(session, reg.user_id, reg.symbol, [*keys, *sorted(triggers)])
    return True


async def daily_round(
    bot: Bot, deps: Deps, now: datetime | None = None, title_note: str = TITLE
) -> int:
    now = now or datetime.now(UTC)
    with deps.session_factory() as session:
        registrations = active_registrations(session)
        previous_eod = last_eod(session)
    if not registrations:
        return 0

    # Kegagalan satu saham, apa pun jenisnya, tidak boleh menghentikan putaran untuk pengguna lain.
    snaps: dict[str, TickerSnapshot] = {}
    async with deps.make_client() as client:
        for symbol in sorted({r.symbol for r in registrations}):
            try:
                with deps.session_factory() as session:
                    snaps[symbol] = await prepare(
                        client,
                        session,
                        symbol,
                        fill_peers=deps.fill_gaps,
                        fill_broker=deps.fill_gaps,
                    )
            except Exception:
                log.exception("putaran: data %s gagal diambil", symbol)
    if not snaps:
        return 0
    eod = max(s.as_of for s in snaps.values())
    if previous_eod is not None and eod <= previous_eod:
        log.info("putaran berhenti: data EOD %s belum maju", eod)
        return 0

    docs = {}
    with deps.session_factory() as session:
        for symbol, snap in snaps.items():
            try:
                before = latest_risk_docs(session, symbol, 1, before=snap.as_of)
                previous = before[0] if before else None
                doc = annotate(
                    build_indicators(snap, trigger="putaran_harian"), previous
                )
                save_risk_doc(session, doc)
                docs[symbol] = (doc, previous)
            except Exception:
                log.exception("putaran: penilaian %s gagal", symbol)

    narrated: dict[str, Checked | None] = {}

    async def narration(symbol: str) -> Checked | None:
        if symbol not in narrated:
            doc = docs[symbol][0]
            narrated[symbol] = await deps.narrate(doc) if deps.narrate else None
        return narrated[symbol]

    sent = 0
    for user_id, group in groupby(registrations, key=lambda r: r.user_id):
        complete = True
        with deps.session_factory() as session:
            since = get_last_round(session, user_id) or now
            for reg in group:
                if reg.symbol not in docs:
                    complete = False
                    continue
                try:
                    sent += await deliver(
                        bot,
                        session,
                        reg,
                        docs[reg.symbol],
                        snaps[reg.symbol],
                        since,
                        narration,
                        title_note,
                    )
                except Exception:
                    log.exception("putaran: alert %s ke %s gagal", reg.symbol, user_id)
                    complete = False
            if complete:
                set_last_round(session, user_id, now)
    with deps.session_factory() as session:
        mark_eod(session, eod)
    return sent


async def weekly_round(deps: Deps) -> None:
    try:
        count = await refresh_notations()
        log.info("notasi khusus BEI diperbarui: %d emiten", count)
    except (httpx.HTTPError, ValueError, KeyError):
        log.exception("notasi khusus BEI gagal diperbarui; CSV lama tetap dipakai")
    with deps.session_factory() as session:
        symbols = sorted({r.symbol for r in active_registrations(session)})
        snaps = [s for sym in symbols if (s := latest_snapshot(session, sym))]
    groups = {}
    for snap in snaps:
        key = (snap.sub_sector, snap.sector == FINANCIAL_SECTOR)
        groups[key] = max(groups.get(key, snap.as_of), snap.as_of)
    async with deps.make_client() as client:
        for (sub_sector, financial), as_of in sorted(groups.items()):
            try:
                with deps.session_factory() as session:
                    await refresh_peer_stats(
                        client, session, sub_sector, financial, as_of
                    )
            except FETCH_ERRORS:
                log.exception("distribusi %s gagal diperbarui", sub_sector)


def schedule(app: Application, deps: Deps) -> tuple[Job, Job]:
    async def run_daily(context: ContextTypes.DEFAULT_TYPE) -> None:
        await daily_round(context.bot, deps)

    async def run_weekly(context: ContextTypes.DEFAULT_TYPE) -> None:
        await weekly_round(deps)

    queue = app.job_queue
    return (
        queue.run_daily(run_daily, DAILY_AT, days=WEEKDAYS, name="putaran_harian"),
        queue.run_daily(run_weekly, WEEKLY_AT, days=MONDAY, name="putaran_mingguan"),
    )
