import copy
from typing import Any

from bot.risk import thresholds as t


def indicators(doc: dict[str, Any]) -> list[dict[str, Any]]:
    return [i for p in doc["pillars"] for i in p["indicators"]]


def annotate(doc: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
    if previous is None:
        return doc
    before = {i["id"]: i for i in indicators(previous)}
    doc = copy.deepcopy(doc)
    for ind in indicators(doc):
        old = before.get(ind["id"])
        if old is None:
            continue
        ind["is_new"] = old["status"] != ind["status"]
        ind["since"] = (
            doc["as_of"] if ind["is_new"] else old["since"] or previous["as_of"]
        )
    return doc


def score_change(doc: dict[str, Any], previous: dict[str, Any] | None) -> str | None:
    old, new = (previous or {}).get("score", {}), doc["score"]
    if old.get("value") is None or new["value"] is None:
        return None
    shift = new["value"] - old["value"]
    if old["grade"] == new["grade"] and abs(shift) < t.ALERT_SCORE_SHIFT:
        return None
    change = (
        f"Skor {'naik' if shift > 0 else 'turun'} dari {old['value']} ke {new['value']}"
    )
    if old["grade"] != new["grade"]:
        change += f", grade {old['grade']} ke {new['grade']}"
    return change


def fresh_problems(doc: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        i
        for i in indicators(doc)
        if i["is_new"] and i["status"] == "bermasalah" and i["dismissed_reason"] is None
    ]


def trigger_keys(doc: dict[str, Any], previous: dict[str, Any] | None) -> set[str]:
    keys = {
        f"pemicu:{doc['as_of']}:{i['id']}"
        for i in fresh_problems(doc)
        if i["source_type"] == "regulator"
    }
    if change := score_change(doc, previous):
        keys.add(f"pemicu:{doc['as_of']}:{change}")
    return keys


def alert_reasons(
    doc: dict[str, Any],
    previous: dict[str, Any] | None,
    events: list[str],
    explanations: dict[str, str] | None = None,
    quiet: bool = False,
) -> list[str]:
    if quiet:
        return list(events)
    change = score_change(doc, previous)
    fresh = fresh_problems(doc)
    regulator = [i for i in fresh if i["source_type"] == "regulator"]
    if not (change or regulator or events):
        return []
    others = [i for i in fresh if i["source_type"] != "regulator"]
    return (
        ([change] if change else [])
        + [
            f"Baru bermasalah: {i['label']} — {(explanations or {}).get(i['id']) or i['display']}"
            for i in regulator + others
        ]
        + events
    )
