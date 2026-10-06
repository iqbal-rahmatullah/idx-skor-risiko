import copy
import json
from pathlib import Path

from bot.risk.compare import alert_reasons, annotate

GOLDEN = Path(__file__).parent / "golden"


def golden(symbol: str) -> dict:
    return json.loads((GOLDEN / f"indicators_{symbol}.json").read_text())


def next_day(doc: dict, as_of: str = "2026-09-23", **statuses: str) -> dict:
    new = copy.deepcopy(doc)
    new["as_of"] = as_of
    for pillar in new["pillars"]:
        for ind in pillar["indicators"]:
            if ind["id"] in statuses:
                ind["status"] = statuses[ind["id"]]
    return new


def indicator(doc: dict, ind_id: str) -> dict:
    return next(i for p in doc["pillars"] for i in p["indicators"] if i["id"] == ind_id)


def test_annotate_marks_changes_and_carries_since():
    day1 = golden("ANTM")
    day2 = annotate(next_day(day1, special_monitoring_board="bermasalah"), day1)
    day3 = annotate(next_day(day2, "2026-09-24"), day2)

    assert indicator(day2, "special_monitoring_board")["is_new"] is True
    assert indicator(day2, "special_monitoring_board")["since"] == "2026-09-23"
    assert indicator(day2, "free_float")["is_new"] is False
    assert indicator(day2, "free_float")["since"] == "2026-09-22"
    assert indicator(day3, "special_monitoring_board")["is_new"] is False
    assert indicator(day3, "special_monitoring_board")["since"] == "2026-09-23"
    assert annotate(day1, None) == day1


def test_no_reason_when_nothing_changed():
    day1 = golden("ANTM")

    assert alert_reasons(annotate(next_day(day1), day1), day1, []) == []


def test_grade_change_and_score_shift():
    day1 = golden("ANTM")
    jump = next_day(day1)
    jump["score"] = {"value": 22, "grade": "B", "scale": "0–100"}
    drift = next_day(day1)
    drift["score"] = {"value": 16, "grade": "A", "scale": "0–100"}
    shift = next_day(day1)
    shift["score"] = {"value": 19, "grade": "A", "scale": "0–100"}

    assert alert_reasons(jump, day1, []) == ["Skor naik dari 7 ke 22, grade A ke B"]
    assert alert_reasons(drift, day1, []) == []
    assert alert_reasons(shift, day1, []) == ["Skor naik dari 7 ke 19"]


def test_regulator_indicator_newly_problematic_but_not_data_ones():
    day1 = golden("ANTM")
    day2 = annotate(
        next_day(
            day1, special_monitoring_board="bermasalah", volume_spike="bermasalah"
        ),
        day1,
    )

    reasons = alert_reasons(day2, day1, [])

    assert reasons[0].startswith("Baru bermasalah: Papan Pemantauan Khusus")
    assert reasons[1].startswith("Baru bermasalah: Lonjakan volume")


def test_data_indicators_alone_do_not_trigger_an_alert():
    day1 = golden("ANTM")
    day2 = annotate(next_day(day1, volume_spike="bermasalah"), day1)

    assert alert_reasons(day2, day1, []) == []
    assert alert_reasons(day2, day1, ["Berita: x"]) == [
        (
            "Baru bermasalah: Lonjakan volume — 80.058.600 lembar hari ini;"
            " persentil 95 90 hari: 171.720.660 lembar"
        ),
        "Berita: x",
    ]


def test_events_are_reasons_on_their_own():
    day1 = golden("ANTM")

    assert alert_reasons(next_day(day1), day1, ["Berita: Laba naik"]) == [
        "Berita: Laba naik"
    ]
