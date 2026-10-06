import argparse
import asyncio
import json
import time

from bot.config import Settings
from bot.narrate.gate import check
from bot.narrate.llm import llm_client, narrate
from bot.risk.__main__ import run


async def report(symbol: str) -> str:
    settings = Settings()
    client = llm_client(settings)
    if client is None:
        raise SystemExit("LLM_BASE_URL dan LLM_MODEL belum diisi di .env")
    doc = json.loads(await run(symbol))
    started = time.monotonic()
    narration = await narrate(client, settings.llm_model, doc, settings.llm_timeout)
    if narration is None:
        raise SystemExit("narasi AI gagal; bot akan mengirim kartu cadangan")
    checked = check(narration, doc)
    result = {
        "symbol": symbol,
        "seconds": round(time.monotonic() - started, 1),
        "summary": checked.summary,
        "verdicts": checked.verdicts,
        "explanations": checked.explanations,
        "news": checked.news,
        "dropped": checked.dropped,
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Narasi AI satu saham dan kalimat yang dibuang gerbang angka."
    )
    parser.add_argument("symbol")
    print(asyncio.run(report(parser.parse_args().symbol.upper())))


if __name__ == "__main__":
    main()
