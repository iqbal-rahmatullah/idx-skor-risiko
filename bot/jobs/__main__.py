import argparse
import asyncio
import logging

from telegram import Bot

from bot.config import Settings
from bot.db import make_session_factory
from bot.jobs.rounds import daily_round, weekly_round
from bot.sectors.client import make_client
from bot.telegram.render import make_narrator
from bot.telegram.services import Deps


async def run(kind: str) -> None:
    settings = Settings()
    deps = Deps(
        session_factory=make_session_factory(settings.database_url),
        make_client=lambda: make_client(settings),
        narrate=make_narrator(settings),
        fill_gaps=settings.sectors_offline,
    )
    if kind == "mingguan":
        await weekly_round(deps)
        return
    async with Bot(settings.telegram_bot_token.get_secret_value()) as bot:
        sent = await daily_round(bot, deps)
    print(f"putaran harian selesai: {sent} pesan terkirim")


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    # httpx mencatat URL Bot API yang memuat token pada level INFO.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser(
        description="Picu putaran secara manual, di luar jadwal JobQueue."
    )
    parser.add_argument("kind", choices=("harian", "mingguan"))
    asyncio.run(run(parser.parse_args().kind))


if __name__ == "__main__":
    main()
