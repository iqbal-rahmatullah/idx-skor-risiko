import logging
from collections.abc import Awaitable, Callable
from typing import Any

from openai import AsyncOpenAI

from bot.config import Settings
from bot.narrate.gate import Checked, check
from bot.narrate.llm import llm_client, narrate
from bot.telegram.render_fallback import LIMIT, render_card, visible_len

log = logging.getLogger(__name__)

Narrate = Callable[[dict[str, Any]], Awaitable[Checked | None]]


def narrator_for(client: AsyncOpenAI, model: str, timeout: float) -> Narrate:
    async def run(doc: dict[str, Any]) -> Checked | None:
        # Balasan rusak apa pun (HTML dari proxy, message null, tipe tak terduga) harus jatuh ke hasil tanpa AI.
        try:
            narration = await narrate(client, model, doc, timeout)
            checked = None if narration is None else check(narration, doc)
        except Exception:
            log.exception("narasi AI %s gagal diproses", doc["symbol"])
            return None
        if checked is None:
            return None
        if checked.dropped:
            log.info(
                "gerbang angka membuang %d kalimat narasi %s",
                len(checked.dropped),
                doc["symbol"],
            )
        return checked

    return run


def make_narrator(settings: Settings) -> Narrate | None:
    client = llm_client(settings)
    if client is None:
        return None
    return narrator_for(client, settings.llm_model, settings.llm_timeout)


def card_from(
    doc: dict[str, Any], previous_score: int | None, checked: Checked | None
) -> list[str]:
    plain = render_card(doc, previous_score=previous_score)
    if checked is None:
        return plain
    chunks = render_card(
        doc,
        previous_score=previous_score,
        summary=checked.summary,
        verdicts=checked.verdicts,
        explanations=checked.explanations,
        news=checked.news,
    )
    if any(visible_len(c) > LIMIT for c in chunks):
        log.warning(
            "hasil AI %s melebihi batas pesan, pakai versi tanpa AI", doc["symbol"]
        )
        return plain
    return chunks
