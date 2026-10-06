import asyncio
import json
import logging
import re
from typing import Any

import openai

from bot.config import Settings
from bot.narrate.prompt import build_messages

log = logging.getLogger(__name__)
FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")


def parse_json(text: str) -> dict[str, Any] | None:
    cleaned = FENCE.sub("", text.strip())
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end < start:
        return None
    try:
        data = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


async def narrate(
    client: openai.AsyncOpenAI, model: str, doc: dict[str, Any], timeout: float
) -> dict[str, Any] | None:
    try:
        async with asyncio.timeout(timeout):
            response = await client.chat.completions.create(
                model=model, messages=build_messages(doc)
            )
    except (openai.OpenAIError, TimeoutError) as exc:
        log.warning("narasi AI %s gagal: %s", doc["symbol"], type(exc).__name__)
        return None
    content = response.choices[0].message.content if response.choices else None
    narration = parse_json(content) if content else None
    if narration is None:
        log.warning("narasi AI %s tidak bisa diparse", doc["symbol"])
    return narration


def llm_client(settings: Settings) -> openai.AsyncOpenAI | None:
    if not (settings.llm_base_url and settings.llm_model):
        return None
    return openai.AsyncOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key.get_secret_value() or "tanpa-kunci",
        timeout=settings.llm_timeout,
        max_retries=0,
    )
