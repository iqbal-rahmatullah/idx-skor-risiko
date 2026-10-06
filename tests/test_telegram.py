import asyncio
import re
from types import SimpleNamespace

from telegram.error import BadRequest

from bot.db import active_registrations, get_registration, make_session_factory
from bot.sectors.client import FIXTURES_DIR, SectorsClient, fixture_transport
from bot.telegram import services
from bot.tickers import suggest_tickers

CHAT = 500
USER = 42


class FakeBot:
    def __init__(self, topic_error: bool = False, thread_error: bool = False):
        self.sent: list[tuple[int, int | None, str]] = []
        self.topics: list[str] = []
        self.closed: list[int] = []
        self.reopened: list[int] = []
        self.topic_error = topic_error
        self.thread_error = thread_error

    async def send_message(self, chat_id, text, message_thread_id=None, **kwargs):
        if self.thread_error and message_thread_id is not None:
            raise BadRequest("Message thread not found")
        self.sent.append((chat_id, message_thread_id, text))

    async def create_forum_topic(self, chat_id, name, **kwargs):
        if self.topic_error:
            raise BadRequest("Topics are disabled")
        self.topics.append(name)
        return SimpleNamespace(message_thread_id=100 + len(self.topics))

    async def close_forum_topic(self, chat_id, message_thread_id, **kwargs):
        self.closed.append(message_thread_id)

    async def reopen_forum_topic(self, chat_id, message_thread_id, **kwargs):
        self.reopened.append(message_thread_id)


def deps() -> services.Deps:
    return services.Deps(
        session_factory=make_session_factory("sqlite://"),
        make_client=lambda: SectorsClient(
            "k", transport=fixture_transport(FIXTURES_DIR)
        ),
        fill_gaps=True,
    )


def texts(bot: FakeBot) -> str:
    return "\n".join(t for _, _, t in bot.sent)


def test_suggest_tickers_by_code_and_name():
    assert "ANTM" in suggest_tickers("ANTN")
    assert "ANTM" in suggest_tickers("aneka tambang")


def test_risk_unknown_ticker_suggests_without_api():
    bot = FakeBot()

    asyncio.run(services.risk(bot, deps(), CHAT, "ANTN"))

    assert len(bot.sent) == 1
    assert "ANTM" in bot.sent[0][2]
    assert "tidak dikenal" in bot.sent[0][2]


def test_risk_without_argument_explains_usage():
    bot = FakeBot()

    asyncio.run(services.risk(bot, deps(), CHAT, ""))

    assert "/risk KODE" in bot.sent[0][2]


def test_risk_sends_ack_then_card_in_main_chat():
    bot = FakeBot()

    asyncio.run(services.risk(bot, deps(), CHAT, "antm"))

    assert bot.sent[0][2] == "⏳ Menilai ANTM… hasil menyusul."
    assert all(thread is None for _, thread, _ in bot.sent)
    assert "Skor tinggi berarti risiko tinggi." in texts(bot)
    assert "Bukan rekomendasi beli atau jual." in texts(bot)


def test_regis_creates_topic_and_sends_card_there():
    bot, d = FakeBot(), deps()

    asyncio.run(services.register(bot, d, USER, CHAT, "ANTM"))

    assert bot.topics == ["ANTM"]
    assert "Hasil penilaian awal menyusul." in texts(bot)
    assert "kartu" not in texts(bot).lower()
    card = [t for _, thread, t in bot.sent if thread == 101]
    assert any("Skor tinggi berarti risiko tinggi." in t for t in card)
    with d.session_factory() as s:
        assert get_registration(s, USER, "ANTM").thread_id == 101


def test_regis_without_topics_still_registers_and_uses_main_chat():
    bot, d = FakeBot(topic_error=True), deps()

    asyncio.run(services.register(bot, d, USER, CHAT, "ANTM"))

    assert all(thread is None for _, thread, _ in bot.sent)
    assert "chat ini" in texts(bot)
    assert "Skor tinggi berarti risiko tinggi." in texts(bot)
    with d.session_factory() as s:
        reg = get_registration(s, USER, "ANTM")
        assert reg.active and reg.thread_id is None


def test_card_falls_back_to_main_chat_when_topic_send_fails():
    bot, d = FakeBot(thread_error=True), deps()

    asyncio.run(services.register(bot, d, USER, CHAT, "ANTM"))

    assert "Skor tinggi berarti risiko tinggi." in texts(bot)
    assert all(thread is None for _, thread, _ in bot.sent)


def test_regis_twice_does_not_create_second_topic():
    bot, d = FakeBot(), deps()

    asyncio.run(services.register(bot, d, USER, CHAT, "ANTM"))
    asyncio.run(services.register(bot, d, USER, CHAT, "ANTM"))

    assert bot.topics == ["ANTM"]
    assert "sudah dipantau" in bot.sent[-1][2]


def test_unregis_closes_topic_and_reregis_reopens_it():
    bot, d = FakeBot(), deps()

    asyncio.run(services.register(bot, d, USER, CHAT, "ANTM"))
    asyncio.run(services.unregister(bot, d, USER, CHAT, "ANTM"))

    assert bot.closed == [101]
    with d.session_factory() as s:
        assert active_registrations(s, USER) == []

    asyncio.run(services.register(bot, d, USER, CHAT, "ANTM"))
    assert bot.reopened == [101]
    assert bot.topics == ["ANTM"]


def test_unregis_unknown_registration():
    bot = FakeBot()

    asyncio.run(services.unregister(bot, deps(), USER, CHAT, "ANTM"))

    assert "tidak sedang dipantau" in bot.sent[0][2]


def test_list_reads_scores_without_api():
    bot, d = FakeBot(), deps()
    asyncio.run(services.register(bot, d, USER, CHAT, "ANTM"))
    asyncio.run(services.register(bot, d, USER, CHAT, "BBCA"))
    bot.sent.clear()

    d.make_client = lambda: (_ for _ in ()).throw(AssertionError("tidak boleh ada API"))
    asyncio.run(services.list_registrations(bot, d, USER, CHAT))

    text = bot.sent[0][2]
    assert "<pre>" in text and "ANTM" in text and "BBCA" in text


def test_list_empty():
    bot = FakeBot()

    asyncio.run(services.list_registrations(bot, deps(), USER, CHAT))

    assert "/regis" in bot.sent[0][2]


def test_install_registers_all_commands():
    from telegram.ext import Application, CommandHandler

    from bot.telegram.handlers import COMMANDS, install

    app = Application.builder().token("123:abc").build()
    install(app, deps())

    commands = {
        c for h in app.handlers[0] if isinstance(h, CommandHandler) for c in h.commands
    }
    assert {name for name, _ in COMMANDS} <= commands
    assert "start" in commands


def test_menu_commands_are_valid_for_telegram():
    from bot.telegram.handlers import COMMANDS

    names = [name for name, _ in COMMANDS]
    assert names[-1] == "help" and len(names) == len(set(names))
    for name, description in COMMANDS:
        assert re.fullmatch(r"[a-z0-9_]{1,32}", name)
        assert 1 <= len(description) <= 256


def test_rejected_ai_card_is_resent_without_ai():
    from telegram.error import BadRequest as Rejected

    from bot.narrate.gate import Checked

    class Picky(FakeBot):
        async def send_message(self, chat_id, text, message_thread_id=None, **_):
            if "KALIMAT AI" in text:
                raise Rejected("Can't parse entities")
            await super().send_message(
                chat_id=chat_id, text=text, message_thread_id=message_thread_id
            )

    async def narrate(doc):
        return Checked(summary="KALIMAT AI yang ditolak Telegram.")

    bot, d = Picky(), deps()
    d.narrate = narrate

    asyncio.run(services.risk(bot, d, CHAT, "ANTM"))

    assert "Skor tinggi berarti risiko tinggi." in texts(bot)
    assert "KALIMAT AI" not in texts(bot)
