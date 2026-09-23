import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from bot.config import Settings


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Halo, bot Skor Risiko aktif.")


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    token = Settings().telegram_bot_token.get_secret_value()
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.run_polling()


if __name__ == "__main__":
    main()
