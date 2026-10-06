import logging

from telegram.ext import AIORateLimiter, Application

from bot.config import Settings
from bot.db import make_session_factory
from bot.jobs.rounds import schedule
from bot.sectors.client import make_client
from bot.telegram import handlers, services
from bot.telegram.render import make_narrator


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    # httpx mencatat URL Bot API yang memuat token pada level INFO.
    logging.getLogger("httpx").setLevel(logging.WARNING)

    settings = Settings()
    dependencies = services.Deps(
        session_factory=make_session_factory(settings.database_url),
        make_client=lambda: make_client(settings),
        narrate=make_narrator(settings),
        fill_gaps=settings.sectors_offline,
    )
    app = (
        Application.builder()
        .token(settings.telegram_bot_token.get_secret_value())
        .rate_limiter(AIORateLimiter())
        .concurrent_updates(True)
        .post_init(handlers.set_commands)
        .build()
    )
    handlers.install(app, dependencies)
    schedule(app, dependencies)
    app.run_polling()


if __name__ == "__main__":
    main()
