import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy.orm import Session, sessionmaker
from telegram import Bot, LinkPreviewOptions
from telegram.constants import ParseMode
from telegram.error import BadRequest, TelegramError

from bot.assess import prepare
from bot.db import (
    active_registrations,
    deactivate,
    get_last_round,
    get_registration,
    latest_risk_docs,
    save_risk_doc,
    set_last_round,
    upsert_registration,
)
from bot.risk.build_json import build_indicators
from bot.risk.compare import annotate
from bot.sectors.client import SectorsClient, SectorsError
from bot.telegram.render import Narrate, card_from
from bot.telegram.render_fallback import esc
from bot.tickers import suggest_tickers, valid_ticker

log = logging.getLogger(__name__)

HELP = (
    "👋 <b>Halo!</b> Saya menilai risiko saham IDX dari 28 indikator dan"
    " menjelaskannya untuk investor pemula.\n\n"
    "🔎 /risk KODE — nilai satu saham, misalnya /risk ANTM\n"
    "📌 /regis KODE — pantau saham; kabarnya dikirim ke topik sendiri\n"
    "📋 /list — daftar saham yang dipantau\n"
    "🛑 /unregis KODE — berhenti memantau\n\n"
    "Semua perintah juga ada di tombol <b>Menu</b> di samping kolom ketik.\n\n"
    "<i>Skor tinggi berarti risiko tinggi. Bukan rekomendasi beli atau jual.</i>"
)
FETCH_ERRORS = (SectorsError, httpx.HTTPError)


@dataclass
class Deps:
    session_factory: sessionmaker[Session]
    make_client: Callable[[], SectorsClient]
    narrate: Narrate | None = None
    # Mengisi distribusi subsektor dan riwayat broker saat kosong; di mode live itu memakan kredit.
    fill_gaps: bool = False


async def send_html(
    bot: Bot, chat_id: int, text: str, thread_id: int | None = None
) -> None:
    await bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode=ParseMode.HTML,
        message_thread_id=thread_id,
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )


async def send_card(
    bot: Bot, chat_id: int, chunks: list[str], thread_id: int | None = None
) -> int | None:
    for chunk in chunks:
        try:
            await send_html(bot, chat_id, chunk, thread_id)
        except TelegramError:
            if thread_id is None:
                raise
            log.warning("kirim ke topik %s gagal, pindah ke chat utama", thread_id)
            thread_id = None
            await send_html(bot, chat_id, chunk)
    return thread_id


def unknown_ticker(text: str) -> str:
    message = f"Ticker <b>{esc(text.strip())}</b> tidak dikenal."
    if suggestions := suggest_tickers(text):
        message += f" Mungkin maksud Anda: {', '.join(suggestions)}?"
    return message


async def assess(
    deps: Deps, symbol: str, backfill_broker: bool = False
) -> tuple[dict[str, Any], int | None]:
    async with deps.make_client() as client:
        with deps.session_factory() as session:
            snap = await prepare(
                client,
                session,
                symbol,
                fill_peers=deps.fill_gaps,
                fill_broker=deps.fill_gaps or backfill_broker,
            )
            before = latest_risk_docs(session, symbol, 1, before=snap.as_of)
            previous = before[0] if before else None
            doc = annotate(build_indicators(snap), previous)
            save_risk_doc(session, doc)
    return doc, previous["score"]["value"] if previous else None


async def assess_and_send(
    bot: Bot,
    deps: Deps,
    chat_id: int,
    symbol: str,
    thread_id: int | None = None,
    backfill_broker: bool = False,
) -> None:
    try:
        doc, previous_score = await assess(deps, symbol, backfill_broker)
    except FETCH_ERRORS:
        log.exception("gagal menilai %s", symbol)
        await send_html(
            bot,
            chat_id,
            f"Data {symbol} belum bisa diambil. Coba lagi beberapa menit lagi.",
            thread_id,
        )
        return
    checked = await deps.narrate(doc) if deps.narrate else None
    try:
        await send_card(
            bot, chat_id, card_from(doc, previous_score, checked), thread_id
        )
    except BadRequest:
        if checked is None:
            raise
        log.warning("hasil AI %s ditolak Telegram, kirim versi tanpa AI", symbol)
        await send_card(bot, chat_id, card_from(doc, previous_score, None), thread_id)


async def risk(bot: Bot, deps: Deps, chat_id: int, text: str) -> None:
    if not text.strip():
        await send_html(bot, chat_id, "Ketik /risk KODE, misalnya /risk ANTM.")
        return
    symbol = valid_ticker(text)
    if symbol is None:
        await send_html(bot, chat_id, unknown_ticker(text))
        return
    await send_html(bot, chat_id, f"⏳ Menilai {symbol}… hasil menyusul.")
    await assess_and_send(bot, deps, chat_id, symbol)


async def open_topic(
    bot: Bot, chat_id: int, symbol: str, old_thread: int | None
) -> int | None:
    if old_thread is not None:
        try:
            await bot.reopen_forum_topic(chat_id=chat_id, message_thread_id=old_thread)
            return old_thread
        except TelegramError:
            log.warning("topik lama %s tidak bisa dibuka ulang", old_thread)
    try:
        topic = await bot.create_forum_topic(chat_id=chat_id, name=symbol)
    except TelegramError:
        log.warning("topik %s tidak bisa dibuat, pakai chat utama", symbol)
        return None
    return topic.message_thread_id


async def register(bot: Bot, deps: Deps, user_id: int, chat_id: int, text: str) -> None:
    if not text.strip():
        await send_html(bot, chat_id, "Ketik /regis KODE, misalnya /regis ANTM.")
        return
    symbol = valid_ticker(text)
    if symbol is None:
        await send_html(bot, chat_id, unknown_ticker(text))
        return
    with deps.session_factory() as session:
        reg = get_registration(session, user_id, symbol)
        if reg is not None and reg.active:
            where = f" Kabarnya ada di topik {symbol}." if reg.thread_id else ""
            await send_html(bot, chat_id, f"{symbol} sudah dipantau.{where}")
            return
        old_thread = reg.thread_id if reg is not None else None
    thread_id = await open_topic(bot, chat_id, symbol, old_thread)
    with deps.session_factory() as session:
        upsert_registration(
            session,
            user_id=user_id,
            chat_id=chat_id,
            symbol=symbol,
            thread_id=thread_id,
        )
        if get_last_round(session, user_id) is None:
            set_last_round(session, user_id, datetime.now(UTC))
    where = (
        f"Kabarnya akan dikirim ke topik {symbol}."
        if thread_id
        else f"Topik tidak bisa dibuat, jadi kabar {symbol} dikirim di chat ini."
    )
    await send_html(
        bot, chat_id, f"✅ {symbol} dipantau. {where} Hasil penilaian awal menyusul."
    )
    await assess_and_send(bot, deps, chat_id, symbol, thread_id, backfill_broker=True)


async def unregister(
    bot: Bot, deps: Deps, user_id: int, chat_id: int, text: str
) -> None:
    symbol = valid_ticker(text) or esc(text.strip().upper())
    with deps.session_factory() as session:
        reg = get_registration(session, user_id, symbol)
        if reg is None or not reg.active:
            await send_html(bot, chat_id, f"{symbol} tidak sedang dipantau.")
            return
        thread_id = reg.thread_id
        deactivate(session, user_id=user_id, symbol=symbol)
    if thread_id is not None:
        try:
            await bot.close_forum_topic(chat_id=chat_id, message_thread_id=thread_id)
        except TelegramError:
            log.warning("topik %s tidak bisa ditutup", thread_id)
    await send_html(
        bot,
        chat_id,
        f"{symbol} tidak lagi dipantau. Topiknya ditutup, riwayatnya tetap bisa dibaca.",
    )


def trend(docs: list[dict[str, Any]]) -> str:
    if len(docs) < 2 or docs[0]["score"]["value"] is None:
        return "baru"
    previous = docs[1]["score"]["value"]
    if previous is None:
        return "baru"
    delta = docs[0]["score"]["value"] - previous
    return "tetap" if delta == 0 else f"{'▲' if delta > 0 else '▼'}{abs(delta)}"


async def list_registrations(bot: Bot, deps: Deps, user_id: int, chat_id: int) -> None:
    with deps.session_factory() as session:
        rows = [
            (reg.symbol, latest_risk_docs(session, reg.symbol, 2))
            for reg in active_registrations(session, user_id)
        ]
    if not rows:
        await send_html(
            bot,
            chat_id,
            "Belum ada saham yang dipantau. Pakai /regis KODE untuk mulai.",
        )
        return
    lines = ["Kode   Skor  Grade  Arah"]
    for symbol, docs in rows:
        if not docs:
            lines.append(f"{symbol:<6} {'-':>4}  {'-':<5}  belum dinilai")
            continue
        score = docs[0]["score"]
        value = "-" if score["value"] is None else str(score["value"])
        lines.append(
            f"{symbol:<6} {value:>4}  {score['grade'] or '-':<5}  {trend(docs)}"
        )
    await send_html(
        bot,
        chat_id,
        "<b>Saham yang dipantau</b>\n<pre>"
        + esc("\n".join(lines))
        + "</pre>\n<i>Skor tinggi berarti risiko tinggi. ▲ risiko naik, ▼ risiko turun.</i>",
    )
