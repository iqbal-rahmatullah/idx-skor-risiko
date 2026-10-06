import logging

from telegram import BotCommand, Update
from telegram.ext import Application, CommandHandler, ContextTypes

from bot.telegram import services

log = logging.getLogger(__name__)

COMMANDS = (
    ("risk", "Cek risiko saham (contoh: /risk ANTM)"),
    ("regis", "Pantau saham, dikabari tiap pagi"),
    ("list", "Saham yang Anda pantau"),
    ("unregis", "Berhenti memantau saham"),
    ("help", "Cara memakai bot"),
)


def deps(context: ContextTypes.DEFAULT_TYPE) -> services.Deps:
    return context.bot_data["deps"]


def argument(context: ContextTypes.DEFAULT_TYPE) -> str:
    return " ".join(context.args or [])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await services.send_html(context.bot, update.effective_chat.id, services.HELP)


async def risk(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await services.risk(
        context.bot, deps(context), update.effective_chat.id, argument(context)
    )


async def regis(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await services.register(
        context.bot,
        deps(context),
        update.effective_user.id,
        update.effective_chat.id,
        argument(context),
    )


async def unregis(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await services.unregister(
        context.bot,
        deps(context),
        update.effective_user.id,
        update.effective_chat.id,
        argument(context),
    )


async def list_(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await services.list_registrations(
        context.bot, deps(context), update.effective_user.id, update.effective_chat.id
    )


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.error("gagal menangani update", exc_info=context.error)
    if isinstance(update, Update) and update.effective_chat:
        await services.send_html(
            context.bot,
            update.effective_chat.id,
            "Maaf, ada kesalahan saat memproses perintah. Coba lagi sebentar lagi.",
        )


async def set_commands(app: Application) -> None:
    await app.bot.set_my_commands([BotCommand(name, text) for name, text in COMMANDS])


def install(app: Application, dependencies: services.Deps) -> None:
    app.bot_data["deps"] = dependencies
    for name, callback in (
        ("start", start),
        ("help", start),
        ("risk", risk),
        ("regis", regis),
        ("unregis", unregis),
        ("list", list_),
    ):
        app.add_handler(CommandHandler(name, callback))
    app.add_error_handler(on_error)
