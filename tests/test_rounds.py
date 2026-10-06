import asyncio
import csv
import shutil
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from telegram.error import TelegramError
from telegram.ext import Application

from bot.db import (
    get_last_round,
    last_eod,
    latest_risk_docs,
    make_session_factory,
    set_last_round,
    upsert_registration,
)
from bot.demo import next_day_overlay
from bot.idx import lists
from bot.idx.lists import idx_lists_for
from bot.idx.refresh import refresh_notations
from bot.jobs.rounds import (
    DAILY_AT,
    JAKARTA,
    WEEKDAYS,
    daily_round,
    schedule,
    weekly_round,
)
from bot.sectors.client import FIXTURES_DIR, SectorsClient, fixture_transport
from bot.telegram.services import Deps

DAY2 = date(2026, 9, 23)


class FakeBot:
    def __init__(self, broken_threads: set[int] = frozenset()) -> None:
        self.sent: list[dict] = []
        self.broken = broken_threads

    async def send_message(self, **kwargs) -> None:
        if kwargs.get("message_thread_id") in self.broken:
            raise TelegramError("topik ditutup")
        self.sent.append(kwargs)


def wib(day: date, hour: int) -> datetime:
    return datetime(day.year, day.month, day.day, hour, tzinfo=JAKARTA).astimezone(UTC)


def deps_for(session_factory, *overlays: Path) -> Deps:
    return Deps(
        session_factory=session_factory,
        make_client=lambda: SectorsClient(
            "k", transport=fixture_transport(FIXTURES_DIR, *overlays)
        ),
        fill_gaps=True,
    )


def with_monitoring_board(src: Path, dst: Path, symbol: str) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    shutil.copy(src / "hsc.csv", dst / "hsc.csv")
    with (src / "notasi_khusus.csv").open(newline="") as f:
        rows = list(csv.DictReader(f))
    fields = list(rows[0])
    rows.append(
        {
            **rows[0],
            "kode": symbol,
            "notasi": "X",
            "keterangan": "X : Papan Pemantauan Khusus",
        }
    )
    with (dst / "notasi_khusus.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_rounds_travel_through_time(tmp_path, monkeypatch):
    session_factory = make_session_factory("sqlite://")
    with session_factory() as session:
        upsert_registration(
            session, user_id=1, chat_id=100, symbol="ANTM", thread_id=11
        )
        upsert_registration(
            session, user_id=1, chat_id=100, symbol="BBCA", thread_id=12
        )
        set_last_round(session, 1, wib(date(2026, 9, 22), 6))
    day1 = deps_for(session_factory)

    bot = FakeBot()
    asyncio.run(daily_round(bot, day1, wib(DAY2, 6)))
    assert {m["message_thread_id"] for m in bot.sent} <= {11, 12}
    assert all("Kabar pemantauan" in m["text"] for m in bot.sent)

    again = FakeBot()
    assert asyncio.run(daily_round(again, day1, wib(DAY2, 7))) == 0
    assert again.sent == []

    overlay = tmp_path / "day2"
    for symbol in ("ANTM", "BBCA"):
        next_day_overlay(overlay, symbol, DAY2)
    next_day_overlay(
        overlay,
        "ANTM",
        DAY2,
        news=[{"title": "ANTM dapat izin baru", "timestamp": "2026-09-23T10:00:00"}],
    )
    with_monitoring_board(lists.DATA_DIR, tmp_path / "idx", "ANTM")
    monkeypatch.setattr("bot.idx.lists.DATA_DIR", tmp_path / "idx")

    day2 = FakeBot(broken_threads={11})
    sent = asyncio.run(
        daily_round(
            day2, deps_for(session_factory, overlay), wib(DAY2 + timedelta(1), 6)
        )
    )

    assert sent == 1
    [message] = day2.sent
    assert message["chat_id"] == 100
    assert message.get("message_thread_id") is None
    assert "Baru bermasalah: Papan Pemantauan Khusus" in message["text"]
    assert "ANTM dapat izin baru" in message["text"]
    with session_factory() as session:
        assert last_eod(session) == DAY2
        assert get_last_round(session, 1) == wib(DAY2 + timedelta(1), 6)
        [doc] = latest_risk_docs(session, "ANTM", 1)
        board = next(
            i
            for p in doc["pillars"]
            for i in p["indicators"]
            if i["id"] == "special_monitoring_board"
        )
        assert board["is_new"] is True and board["since"] == "2026-09-23"


def test_round_without_registrations_sends_nothing():
    deps = deps_for(make_session_factory("sqlite://"))

    assert asyncio.run(daily_round(FakeBot(), deps, wib(DAY2, 6))) == 0


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (datetime(2026, 9, 26, 5, tzinfo=UTC), datetime(2026, 9, 27, 23, tzinfo=UTC)),
        (datetime(2026, 9, 29, 22, tzinfo=UTC), datetime(2026, 9, 29, 23, tzinfo=UTC)),
    ],
)
def test_daily_round_fires_at_six_jakarta_on_weekdays(now, expected):
    app = Application.builder().token("123:abc").build()
    deps = deps_for(make_session_factory("sqlite://"))

    daily, weekly = schedule(app, deps)

    assert DAILY_AT.tzinfo == JAKARTA and WEEKDAYS == (1, 2, 3, 4, 5)
    trigger = daily.job.trigger
    assert trigger.get_next_fire_time(None, now).astimezone(UTC) == expected
    monday = weekly.job.trigger.get_next_fire_time(None, now).astimezone(JAKARTA)
    assert monday.weekday() == 0 and monday.hour == 5


def test_weekly_round_refreshes_registered_subsectors(monkeypatch):
    calls = []

    async def fake_refresh():
        raise httpx.ConnectError("idx.id tidak bisa dihubungi")

    async def fake_peers(client, session, sub_sector, financial, as_of):
        calls.append((sub_sector, financial, as_of))

    monkeypatch.setattr("bot.jobs.rounds.refresh_notations", fake_refresh)
    session_factory = make_session_factory("sqlite://")
    deps = deps_for(session_factory)
    with session_factory() as session:
        for symbol in ("BBCA", "BBRI", "ANTM"):
            upsert_registration(
                session, user_id=1, chat_id=1, symbol=symbol, thread_id=None
            )
    asyncio.run(daily_round(FakeBot(), deps, wib(DAY2, 6)))
    monkeypatch.setattr("bot.jobs.rounds.refresh_peer_stats", fake_peers)

    asyncio.run(weekly_round(deps))

    assert calls == [
        ("Banks", True, date(2026, 9, 22)),
        ("Basic Materials", False, date(2026, 9, 22)),
    ]


def test_refresh_notations_writes_loader_compatible_csv(tmp_path):
    body = {
        "Results": [
            {
                "EmitenCode": "ZZZZ",
                "Notation": "E,X",
                "Date": "2026-09-29T00:00:00",
                "Description": "E : ekuitas negatif| X : Papan Pemantauan Khusus ",
            },
            {
                "EmitenCode": "AAAA",
                "Notation": "L",
                "Date": "2026-09-29T00:00:00",
                "Description": None,
            },
        ]
    }
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=body))
    path = tmp_path / "notasi_khusus.csv"

    count = asyncio.run(refresh_notations(path, transport))

    assert count == 2
    assert path.read_text().splitlines()[1].startswith("AAAA,L,2026-09-29,")
    lists = idx_lists_for("ZZZZ", path, tmp_path / "tidak-ada.csv")
    assert lists.notations == ["E", "X"]
    assert lists.as_of == date(2026, 9, 29)


def test_alert_uses_ai_sentences_when_available(tmp_path, monkeypatch):
    from bot.narrate.gate import Checked

    session_factory = make_session_factory("sqlite://")
    with session_factory() as session:
        upsert_registration(
            session, user_id=1, chat_id=100, symbol="ANTM", thread_id=11
        )
        set_last_round(session, 1, wib(date(2026, 9, 22), 6))
    asyncio.run(daily_round(FakeBot(), deps_for(session_factory), wib(DAY2, 6)))

    overlay = tmp_path / "day2"
    next_day_overlay(overlay, "ANTM", DAY2)
    with_monitoring_board(lists.DATA_DIR, tmp_path / "idx", "ANTM")
    monkeypatch.setattr("bot.idx.lists.DATA_DIR", tmp_path / "idx")
    calls = []

    async def narrate(doc):
        calls.append(doc["symbol"])
        return Checked(
            summary="ANTM kini masuk papan khusus untuk saham bermasalah.",
            explanations={
                "special_monitoring_board": "Saham ini sekarang diperdagangkan lewat lelang berkala, jadi lebih sulit dijual."
            },
        )

    deps = deps_for(session_factory, overlay)
    deps.narrate = narrate
    bot = FakeBot()
    asyncio.run(daily_round(bot, deps, wib(DAY2 + timedelta(1), 6)))

    [message] = bot.sent
    assert calls == ["ANTM"]
    assert "ANTM kini masuk papan khusus untuk saham bermasalah." in message["text"]
    assert (
        "Baru bermasalah: Papan Pemantauan Khusus — Saham ini sekarang diperdagangkan"
        in message["text"]
    )
    assert "<b>Papan Pemantauan Khusus</b>: Saham ini sekarang" in message["text"]
    assert "tercatat di Papan Pemantauan Khusus (per" not in message["text"]


def day_one(session_factory, *symbols):
    with session_factory() as session:
        for symbol in symbols:
            upsert_registration(
                session, user_id=1, chat_id=100, symbol=symbol, thread_id=None
            )
        set_last_round(session, 1, wib(date(2026, 9, 22), 6))
    asyncio.run(daily_round(FakeBot(), deps_for(session_factory), wib(DAY2, 6)))


def board_alerts(bot: FakeBot) -> int:
    return sum(
        "Baru bermasalah: Papan Pemantauan Khusus" in m["text"] for m in bot.sent
    )


def test_held_as_of_does_not_repeat_the_same_trigger(tmp_path, monkeypatch):
    session_factory = make_session_factory("sqlite://")
    day_one(session_factory, "ANTM", "BBCA")
    day2 = tmp_path / "d2"
    for symbol in ("ANTM", "BBCA"):
        next_day_overlay(day2, symbol, DAY2)
    with_monitoring_board(lists.DATA_DIR, tmp_path / "idx", "ANTM")
    monkeypatch.setattr("bot.idx.lists.DATA_DIR", tmp_path / "idx")
    second, third = FakeBot(), FakeBot()

    asyncio.run(
        daily_round(
            second, deps_for(session_factory, day2), wib(DAY2 + timedelta(1), 6)
        )
    )
    day3 = tmp_path / "d3"
    shutil.copytree(day2, day3)
    next_day_overlay(day3, "BBCA", DAY2 + timedelta(1))
    asyncio.run(
        daily_round(third, deps_for(session_factory, day3), wib(DAY2 + timedelta(2), 6))
    )

    assert board_alerts(second) == 1
    assert board_alerts(third) == 0


def test_one_failing_stock_does_not_stop_the_round(tmp_path, monkeypatch):
    from bot.jobs import rounds

    session_factory = make_session_factory("sqlite://")
    day_one(session_factory, "ANTM", "BBCA")
    day2 = tmp_path / "d2"
    for symbol in ("ANTM", "BBCA"):
        next_day_overlay(day2, symbol, DAY2)
    with_monitoring_board(lists.DATA_DIR, tmp_path / "idx", "ANTM")
    monkeypatch.setattr("bot.idx.lists.DATA_DIR", tmp_path / "idx")
    real_prepare = rounds.prepare

    async def broken(client, session, symbol, **kwargs):
        if symbol == "BBCA":
            raise ValueError("data BBCA rusak")
        return await real_prepare(client, session, symbol, **kwargs)

    monkeypatch.setattr(rounds, "prepare", broken)
    bot = FakeBot()

    asyncio.run(
        daily_round(bot, deps_for(session_factory, day2), wib(DAY2 + timedelta(1), 6))
    )

    assert board_alerts(bot) == 1
    with session_factory() as session:
        assert get_last_round(session, 1) == wib(DAY2, 6)


def test_failed_send_keeps_events_for_the_next_round(tmp_path):
    session_factory = make_session_factory("sqlite://")
    with session_factory() as session:
        upsert_registration(
            session, user_id=1, chat_id=100, symbol="ANTM", thread_id=None
        )
        set_last_round(session, 1, wib(date(2026, 9, 18), 6))

    class Offline(FakeBot):
        async def send_message(self, **kwargs) -> None:
            raise TelegramError("jaringan putus")

    asyncio.run(daily_round(Offline(), deps_for(session_factory), wib(DAY2, 6)))
    with session_factory() as session:
        assert get_last_round(session, 1) == wib(date(2026, 9, 18), 6)

    retry = FakeBot()
    overlay = tmp_path / "d2"
    next_day_overlay(overlay, "ANTM", DAY2)
    asyncio.run(
        daily_round(
            retry, deps_for(session_factory, overlay), wib(DAY2 + timedelta(1), 6)
        )
    )

    [message] = retry.sent
    assert "Berita 18 September 2026" in message["text"]


def notation_body(n: int, date_text: str = "2026-09-29T00:00:00") -> dict:
    return {
        "Results": [
            {
                "EmitenCode": f"AB{chr(65 + i // 26)}{chr(65 + i % 26)}",
                "Notation": "X",
                "Date": date_text,
                "Description": "X : Papan Pemantauan Khusus",
            }
            for i in range(n)
        ]
    }


def test_refresh_rejects_bad_or_truncated_lists_and_keeps_old_csv(tmp_path):
    path = tmp_path / "notasi_khusus.csv"
    good = httpx.MockTransport(lambda r: httpx.Response(200, json=notation_body(10)))
    assert asyncio.run(refresh_notations(path, good)) >= 1
    before = path.read_text()

    broken = notation_body(10)
    broken["Results"][3]["Date"] = ""
    truncated = {"Results": notation_body(10)["Results"][:1]}
    for body in (broken, truncated):
        transport = httpx.MockTransport(lambda r, b=body: httpx.Response(200, json=b))
        with pytest.raises(ValueError):
            asyncio.run(refresh_notations(path, transport))
        assert path.read_text() == before
    assert not list(tmp_path.glob("*.tmp"))
