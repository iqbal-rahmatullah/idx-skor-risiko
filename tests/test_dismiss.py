from datetime import timedelta

from bot.risk.build_json import build_indicators
from bot.risk.dismiss import catalyst
from bot.snapshot.models import DailyMove
from tests.test_pillars import AS_OF, full_snapshot, series, with_bars


def spiking(symbol: str = "ANTM"):
    closes = [100.0 + (i % 2) for i in range(60)] + [121.0]
    volumes = [1_000] * 60 + [10_000]
    snap = with_bars(full_snapshot(symbol), series(closes, volumes))
    events = snap.events.model_copy(update={"news": [], "corporate_actions": {}})
    return snap.model_copy(update={"events": events, "sector_move": None})


def flagged(doc: dict) -> dict[str, dict]:
    return {
        i["id"]: i
        for p in doc["pillars"]
        for i in p["indicators"]
        if i["id"] in ("volume_spike", "unexplained_move")
    }


def test_spike_without_catalyst_counts():
    doc = build_indicators(spiking())

    assert {i["status"] for i in flagged(doc).values()} == {"bermasalah"}
    assert all(i["dismissed_reason"] is None for i in flagged(doc).values())
    assert doc["dismissed"] == []


def test_sector_wide_move_dismisses_both_flags():
    snap = spiking().model_copy(update={"sector_move": DailyMove(n=10, up=7, down=2)})

    doc = build_indicators(snap)

    reasons = {i["dismissed_reason"] for i in flagged(doc).values()}
    assert reasons == {"7 dari 10 emiten subsektor juga naik pada 22 September 2026"}
    assert [d["id"] for d in doc["dismissed"]] == ["volume_spike", "unexplained_move"]
    assert (
        doc["summary_counts"]["bermasalah"]
        == build_indicators(spiking())["summary_counts"]["bermasalah"] - 2
    )


def test_half_the_sector_is_not_a_majority():
    snap = spiking().model_copy(update={"sector_move": DailyMove(n=10, up=5, down=5)})

    assert catalyst(snap) is None


def test_ex_date_or_news_in_window_dismisses():
    snap = spiking()
    previous_day = (AS_OF - timedelta(days=1)).isoformat()
    dividend = snap.events.model_copy(
        update={"corporate_actions": {"dividend": [{"ex_date": previous_day}]}}
    )
    news = snap.events.model_copy(
        update={
            "news": [
                {"title": "Kontrak baru", "timestamp": f"{AS_OF.isoformat()}T09:00:00"}
            ]
        }
    )
    old_news = snap.events.model_copy(
        update={"news": [{"title": "Lama", "timestamp": "2026-09-01T09:00:00"}]}
    )

    assert catalyst(snap.model_copy(update={"events": dividend})) == (
        "ex-date dividen pada 21 September 2026"
    )
    assert catalyst(snap.model_copy(update={"events": news})) == (
        "ada berita pada 22 September 2026: Kontrak baru"
    )
    assert catalyst(snap.model_copy(update={"events": old_news})) is None


def test_dismissed_flag_does_not_raise_pillar_score():
    counted = build_indicators(spiking())
    snap = spiking().model_copy(update={"sector_move": DailyMove(n=10, up=9, down=0)})
    dismissed = build_indicators(snap)

    pillar = {p["id"]: p["score"] for p in dismissed["pillars"]}
    before = {p["id"]: p["score"] for p in counted["pillars"]}
    assert pillar["perilaku_harga"] < before["perilaku_harga"]
    assert pillar["ukuran_likuiditas"] < before["ukuran_likuiditas"]
    assert dismissed["score"]["value"] < counted["score"]["value"]
