from datetime import UTC, date, datetime

from bot.db import (
    active_registrations,
    alerted_keys,
    deactivate,
    get_last_round,
    get_registration,
    last_eod,
    latest_risk_docs,
    make_session_factory,
    mark_alerted,
    mark_eod,
    price_bars,
    save_price_bars,
    save_risk_doc,
    set_last_round,
    upsert_registration,
)
from bot.snapshot.models import Bar


def doc(symbol: str, as_of: str, score: int) -> dict:
    return {"symbol": symbol, "as_of": as_of, "score": {"value": score, "grade": "A"}}


def test_registration_lifecycle():
    session_factory = make_session_factory("sqlite://")
    with session_factory() as s:
        upsert_registration(s, user_id=1, chat_id=10, symbol="ANTM", thread_id=5)
        upsert_registration(s, user_id=1, chat_id=10, symbol="BBCA", thread_id=None)
        upsert_registration(s, user_id=2, chat_id=20, symbol="ANTM", thread_id=7)

        assert [r.symbol for r in active_registrations(s, user_id=1)] == [
            "ANTM",
            "BBCA",
        ]
        assert len(active_registrations(s)) == 3

        deactivate(s, user_id=1, symbol="ANTM")
        assert get_registration(s, 1, "ANTM").active is False
        assert get_registration(s, 1, "ANTM").closed_at is not None
        assert [r.symbol for r in active_registrations(s, user_id=1)] == ["BBCA"]

        upsert_registration(s, user_id=1, chat_id=10, symbol="ANTM", thread_id=9)
        reg = get_registration(s, 1, "ANTM")
        assert reg.active is True and reg.thread_id == 9 and reg.closed_at is None


def test_risk_docs_newest_first_and_upsert_same_date():
    session_factory = make_session_factory("sqlite://")
    with session_factory() as s:
        save_risk_doc(s, doc("ANTM", "2026-09-21", 10))
        save_risk_doc(s, doc("ANTM", "2026-09-22", 20))
        save_risk_doc(s, doc("ANTM", "2026-09-22", 25))
        save_risk_doc(s, doc("BBCA", "2026-09-22", 5))

        docs = latest_risk_docs(s, "ANTM", 2)
        assert [(d["as_of"], d["score"]["value"]) for d in docs] == [
            ("2026-09-22", 25),
            ("2026-09-21", 10),
        ]
        assert latest_risk_docs(s, "ANTM", 1, before=date(2026, 9, 22))[0]["as_of"] == (
            "2026-09-21"
        )
        assert latest_risk_docs(s, "TLKM", 2) == []


def test_last_round_round_trips_as_utc():
    session_factory = make_session_factory("sqlite://")
    moment = datetime(2026, 9, 22, 23, 0, tzinfo=UTC)
    with session_factory() as s:
        assert get_last_round(s, 1) is None
        set_last_round(s, 1, moment)
        assert get_last_round(s, 1) == moment
        set_last_round(s, 1, datetime(2026, 9, 23, 23, 0, tzinfo=UTC))
        assert get_last_round(s, 1).day == 23


def test_price_bars_accumulate_and_upsert():
    def bar(day: int, close: float) -> Bar:
        return Bar(
            date=date(2026, 9, day), open=1, high=1, low=1, close=close, volume=10
        )

    session_factory = make_session_factory("sqlite://")
    with session_factory() as session:
        save_price_bars(session, "ANTM", [bar(18, 100), bar(21, 101)])
        save_price_bars(session, "ANTM", [bar(21, 105), bar(22, 106)])

        bars = price_bars(session, "ANTM", date(2026, 9, 1), date(2026, 9, 30))

    assert [(b.date.day, b.close) for b in bars] == [(18, 100), (21, 105), (22, 106)]


def test_alerted_events_and_eod_marks():
    session_factory = make_session_factory("sqlite://")
    with session_factory() as session:
        assert last_eod(session) is None
        mark_alerted(session, 1, "ANTM", ["news:a", "news:b"])
        mark_alerted(session, 1, "ANTM", ["news:a"])
        mark_eod(session, date(2026, 9, 21))
        mark_eod(session, date(2026, 9, 22))
        mark_eod(session, date(2026, 9, 22))

        assert alerted_keys(session, 1, "ANTM") == {"news:a", "news:b"}
        assert alerted_keys(session, 2, "ANTM") == set()
        assert last_eod(session) == date(2026, 9, 22)
