import html
import re
from datetime import date
from textwrap import shorten
from typing import Any

from bot.narrate.skill import glossary
from bot.risk.format import day

LIMIT = 4096
ICON = {
    "bermasalah": "🔴",
    "perhatian": "🟡",
    "wajar": "🟢",
    "kuat": "🔵",
    "tidak_tersedia": "⚪",
    "tidak_berlaku": "⚪",
}
WORD = {
    "bermasalah": "bermasalah",
    "perhatian": "perhatian",
    "wajar": "wajar",
    "kuat": "kuat",
    "tidak_tersedia": "tidak terdata",
    "tidak_berlaku": "tidak berlaku",
}
ASSESSABLE = ("kuat", "wajar", "perhatian", "bermasalah")
PILLAR_ICON = {
    "ukuran_likuiditas": "💧",
    "kesehatan_keuangan": "🏦",
    "valuasi": "🏷️",
    "kepemilikan": "👥",
    "perilaku_harga": "📈",
    "peristiwa": "📰",
}
SEVERITY = {
    "bermasalah": 0,
    "perhatian": 1,
    "kuat": 3,
    "wajar": 4,
    "tidak_berlaku": 5,
    "tidak_tersedia": 6,
}
BAR_CELLS = 10
TITLE_MAX = 160
ALERT_MAX_LINES = 8
NEWS_MAX = 5


def esc(text: object) -> str:
    return html.escape(str(text), quote=False)


def visible_len(text: str) -> int:
    plain = html.unescape(re.sub(r"<[^>]+>", "", text))
    return len(plain.encode("utf-16-le")) // 2


def clip(text: str, width: int = TITLE_MAX) -> str:
    return shorten(text, width, placeholder="…")


def sentence(text: str) -> str:
    return text if text.endswith((".", "!", "?")) else f"{text}."


def indicators(doc: dict[str, Any]) -> list[dict[str, Any]]:
    return [ind for pillar in doc["pillars"] for ind in pillar["indicators"]]


def header(
    doc: dict[str, Any],
    previous_score: int | None,
    title_note: str | None,
    summary: str | None,
) -> str:
    title = f"<b>{esc(doc['symbol'])}</b>"
    if doc.get("company_name"):
        title += f" · {esc(doc['company_name'])}"
    if title_note:
        title = f"<b>{esc(title_note)}</b> · {title}"
    score = doc["score"]
    if score["value"] is None:
        score_line = "Skor risiko belum bisa dihitung: data tidak cukup."
    else:
        score_line = (
            f"<b>Skor risiko {score['value']}/100</b> · Grade <b>{score['grade']}</b>"
        )
        if previous_score is not None:
            delta = score["value"] - previous_score
            if delta == 0:
                score_line += " · tetap"
            else:
                score_line += (
                    f" · {'naik' if delta > 0 else 'turun'} dari {previous_score}"
                )
    counts = doc["summary_counts"]
    assessable = sum(counts[s] for s in ASSESSABLE)
    if summary is None:
        summary = (
            f"{counts['bermasalah']} dari {assessable} indikator yang bisa dinilai bermasalah."
            if counts["bermasalah"]
            else f"Tidak ada indikator yang bermasalah dari {assessable} yang bisa dinilai."
        )
    tally = [
        f"{ICON[s]} {counts[s]} {WORD[s]}"
        for s in ("bermasalah", "perhatian", "kuat", "wajar")
        if counts[s]
    ]
    if unrated := counts["tidak_tersedia"] + counts["tidak_berlaku"]:
        tally.append(f"⚪ {unrated} tidak dinilai")
    if doc["dismissed"]:
        tally.append(f"✓ {len(doc['dismissed'])} dibatalkan")
    lines = [title, score_line]
    if score["value"] is not None:
        lines.append(score_bar(score["value"]))
    lines += [
        "<i>Skor tinggi berarti risiko tinggi.</i>",
        "",
        esc(summary),
        " · ".join(tally),
    ]
    return "\n".join(lines)


def score_bar(value: int) -> str:
    filled = min(BAR_CELLS, (value + 5) // 10)
    return "▰" * filled + "▱" * (BAR_CELLS - filled)


def news_lines(doc: dict[str, Any], summaries: dict[str, str]) -> list[str]:
    items = doc.get("context", {}).get("negative_news", [])
    lines = []
    for item in items[:NEWS_MAX]:
        text = esc(summaries.get(item["id"]) or clip(item["title"]))
        source = item.get("source") or ""
        if source.startswith(("https://", "http://")):
            text = f'<a href="{html.escape(source, quote=True)}">{text}</a>'
        lines.append(f"   • {day(date.fromisoformat(item['date']))}: {text}")
    if len(items) > NEWS_MAX:
        lines.append(f"   • dan {len(items) - NEWS_MAX} berita lain")
    return lines


def detail(ind: dict[str, Any], narrated: bool) -> str:
    parts = []
    if not narrated:
        parts.append(sentence(glossary().get(ind["id"], "")))
    elif ind["value"] is not None:
        parts.append(f"Data: {sentence(ind['display'])}")
    if ind["status"] in ASSESSABLE:
        parts.append(f"Ambang: {sentence(ind['threshold'])}")
    if ind.get("note"):
        parts.append(sentence(ind["note"]))
    return esc(" ".join(p for p in parts if p))


def rank(ind: dict[str, Any]) -> int:
    return 2 if ind.get("dismissed_reason") else SEVERITY[ind["status"]]


def pillar_pieces(
    pillar: dict[str, Any],
    verdicts: dict[str, str],
    explanations: dict[str, str],
    extras: dict[str, list[str]],
) -> list[str]:
    score = "tanpa skor" if pillar["score"] is None else f"skor {pillar['score']}"
    icon = PILLAR_ICON.get(pillar["id"], "▪️")
    head = [f"{icon} <b>{esc(pillar['label'])}</b> · {score}"]
    if verdicts.get(pillar["id"]):
        head.append(f"<i>{esc(verdicts[pillar['id']])}</i>")
    if not pillar["indicators"]:
        head.append("Belum ada indikator yang dinilai.")
        return ["\n".join(head)]
    narrated = any(explanations.get(i["id"]) for i in pillar["indicators"])
    rows, numbers = [], []
    for ind in sorted(pillar["indicators"], key=rank):
        mark = "✓" if ind.get("dismissed_reason") else ICON[ind["status"]]
        story = explanations.get(ind["id"])
        text = sentence(story) if story else ind["display"]
        rows.append(f"{mark} <b>{esc(ind['label'])}</b>: {esc(text)}")
        rows += extras.get(ind["id"], [])
        small = detail(ind, bool(story))
        if not small:
            continue
        if narrated:
            numbers.append(f"<i>{esc(ind['label'])}: {small}</i>")
        else:
            rows.append(f"<i>{small}</i>")
    if numbers:
        rows += ["", "📏 <b>Angka dan ambang</b>", *numbers]
    return [
        "\n".join(head),
        "<blockquote expandable>" + "\n".join(rows) + "</blockquote>",
    ]


def dismissed_block(doc: dict[str, Any]) -> str:
    lines = ["✓ <b>Bendera yang dibatalkan</b> (tidak dihitung dalam skor)"]
    lines += [
        f"• {esc(d['label'])}: {esc(d['display'])}."
        f" Penyebab wajar: {esc(sentence(d['reason']))}"
        for d in doc["dismissed"]
    ]
    return "\n".join(lines)


def unavailable_block(doc: dict[str, Any]) -> str:
    labels = [i["label"] for i in indicators(doc) if i["id"] in doc["unavailable"]]
    return f"⚪ <b>Tidak terdata</b>: {esc(', '.join(labels))}."


def footer(doc: dict[str, Any]) -> str:
    as_of = day(date.fromisoformat(doc["as_of"]))
    return f"<i>Data per {as_of}. Bukan rekomendasi beli atau jual.</i>"


def pack(blocks: list[list[str]]) -> list[str]:
    chunks: list[str] = []
    current = ""
    for pieces in blocks:
        whole = "\n".join(pieces)
        units = [whole] if visible_len(whole) <= LIMIT else pieces
        for unit in units:
            candidate = f"{current}\n\n{unit}" if current else unit
            if current and visible_len(candidate) > LIMIT:
                chunks.append(current)
                current = unit
            else:
                current = candidate
    if current:
        chunks.append(current)
    return chunks


def line(ind: dict[str, Any], explanations: dict[str, str]) -> str:
    text = explanations.get(ind["id"])
    text = sentence(text) if text else ind["display"]
    return f"{ICON[ind['status']]} <b>{esc(ind['label'])}</b>: {esc(text)}"


def capped(lines: list[str], what: str) -> list[str]:
    extra = len(lines) - ALERT_MAX_LINES
    return lines[:ALERT_MAX_LINES] + (
        [f"• dan {extra} {what} lain"] if extra > 0 else []
    )


def render_alert(
    doc: dict[str, Any],
    *,
    previous_score: int | None,
    reasons: list[str],
    title_note: str = "🔔 Kabar pemantauan",
    summary: str | None = None,
    explanations: dict[str, str] | None = None,
) -> str:
    inds = indicators(doc)
    problems = [
        i for i in inds if i["status"] == "bermasalah" and not i.get("dismissed_reason")
    ]
    strongest = sorted(
        (i for i in inds if i["status"] in ("kuat", "wajar")),
        key=lambda i: (i["status"] != "kuat", -i["weight"]),
    )[:2]
    parts = [
        header(doc, previous_score, title_note, summary),
        "\n".join(
            ["📣 <b>Yang berubah</b>"]
            + capped([f"• {esc(r)}" for r in reasons], "kabar")
        ),
    ]
    rows = []
    if problems:
        rows.append(f"<b>Bermasalah ({len(problems)})</b>")
        rows += capped([line(i, explanations or {}) for i in problems], "indikator")
    if strongest:
        rows.append("<b>Terkuat</b>")
        rows += [line(i, explanations or {}) for i in strongest]
    if rows:
        parts.append("<blockquote expandable>" + "\n".join(rows) + "</blockquote>")
    if doc["dismissed"]:
        parts.append(dismissed_block(doc))
    parts.append(footer(doc))
    return "\n\n".join(parts)


def render_card(
    doc: dict[str, Any],
    *,
    previous_score: int | None = None,
    title_note: str | None = None,
    summary: str | None = None,
    verdicts: dict[str, str] | None = None,
    explanations: dict[str, str] | None = None,
    news: dict[str, str] | None = None,
) -> list[str]:
    extras = {"negative_news": news_lines(doc, news or {})}
    blocks = [[header(doc, previous_score, title_note, summary)]]
    blocks += [
        pillar_pieces(p, verdicts or {}, explanations or {}, extras)
        for p in doc["pillars"]
    ]
    if doc["dismissed"]:
        blocks.append([dismissed_block(doc)])
    if doc["unavailable"]:
        blocks.append([unavailable_block(doc)])
    blocks.append([footer(doc)])
    return pack(blocks)
