import copy
import json
from pathlib import Path

from bot.narrate.skill import glossary
from bot.telegram.render_fallback import LIMIT, render_card, visible_len

GOLDEN = Path(__file__).parent / "golden"


def golden(symbol: str) -> dict:
    return json.loads((GOLDEN / f"indicators_{symbol}.json").read_text())


def test_glossary_covers_every_indicator_and_status():
    terms = glossary()

    for doc in (golden("ANTM"), golden("BBCA")):
        for pillar in doc["pillars"]:
            for ind in pillar["indicators"]:
                assert ind["id"] in terms
    for status in ("kuat", "wajar", "perhatian", "bermasalah", "tidak_tersedia"):
        assert status in terms


def test_card_contains_mandatory_sentences():
    doc = golden("ANTM")
    text = "\n".join(render_card(doc))

    assert "Skor tinggi berarti risiko tinggi." in text
    assert "Bukan rekomendasi beli atau jual." in text
    assert "Data per 22 September 2026" in text
    assert "Grade <b>A</b>" in text
    assert "Kuitansi" not in text
    assert not any(
        i["source_url"] in text for p in doc["pillars"] for i in p["indicators"]
    )


def test_every_indicator_listed_with_display():
    doc = golden("BBCA")
    text = "\n".join(render_card(doc))

    for pillar in doc["pillars"]:
        for ind in pillar["indicators"]:
            assert ind["label"] in text


def big_doc() -> dict:
    doc = copy.deepcopy(golden("ANTM"))
    for pillar in doc["pillars"]:
        template = doc["pillars"][0]["indicators"][0]
        pillar["indicators"] = [
            {**template, "id": f"{pillar['id']}_{i}", "label": f"{pillar['label']} {i}"}
            for i in range(8)
        ]
    return doc


def test_chunks_respect_limit_and_split_only_between_pillars():
    doc = big_doc()
    chunks = render_card(doc)

    assert len(chunks) > 1
    assert all(visible_len(c) <= LIMIT for c in chunks)
    for pillar in doc["pillars"]:
        holders = [c for c in chunks if pillar["label"] + " 0" in c]
        assert len(holders) == 1
        assert all(f"{pillar['label']} {i}" in holders[0] for i in range(8))
    assert "Skor tinggi berarti risiko tinggi." in chunks[0]
    assert "Bukan rekomendasi beli atau jual." in chunks[-1]


def test_html_in_data_is_escaped():
    doc = copy.deepcopy(golden("ANTM"))
    doc["pillars"][0]["indicators"][0]["display"] = "<script>&"

    text = "\n".join(render_card(doc))

    assert "<script>" not in text
    assert "&lt;script&gt;&amp;" in text


def test_score_change_is_described():
    doc = golden("ANTM")

    up = "\n".join(render_card(doc, previous_score=doc["score"]["value"] - 5))
    same = "\n".join(render_card(doc, previous_score=doc["score"]["value"]))

    assert "naik dari" in up
    assert "tetap" in same


def test_dismissed_flags_are_listed_as_not_counted():
    doc = copy.deepcopy(golden("ANTM"))
    doc["dismissed"] = [
        {
            "id": "unexplained_move",
            "label": "Lonjakan harga",
            "display": "+18%",
            "reason": "ada berita pada 23 September 2026",
        }
    ]

    text = "\n".join(render_card(doc))

    assert "Bendera yang dibatalkan" in text
    assert "ada berita pada 23 September 2026" in text


def test_demo_label_and_title_note():
    text = "\n".join(render_card(golden("ANTM"), title_note="SKENARIO DEMO"))

    assert "SKENARIO DEMO" in text.splitlines()[0]


def test_visible_len_counts_utf16_units_like_telegram():
    assert visible_len("🔴 <b>a</b>&amp;") == 5


def test_real_cards_fit_in_three_messages():
    for path in sorted(GOLDEN.glob("indicators_*.json")):
        chunks = render_card(json.loads(path.read_text()))

        assert len(chunks) <= 3, path.stem
        assert all(visible_len(c) <= LIMIT for c in chunks)


def test_ai_sentence_replaces_raw_numbers_in_the_visible_line():
    doc = golden("ANTM")
    example = json.loads(
        (
            Path(__file__).parents[1]
            / "skills/analisis-risiko-saham/references/contoh/ANTM.json"
        ).read_text()
    )
    explanations = {
        k: v for k, v in example["explanations"].items() if k != "drawdown_90d"
    }

    text = "\n".join(render_card(doc, explanations=explanations))

    assert (
        "🟢 <b>Volatilitas 90 hari</b>: Naik-turun harganya 5,66% dalam 90 hari,"
        " jauh lebih tenang dari batas subsektor 22,32%." in text
    )
    assert "Data: 5,66%; persentil 90 Basic Materials: 22,32%." in text
    assert "🟢 <b>Penurunan terdalam 90 hari</b>: 8,97%; persentil 90" in text
    assert "🟢 Volatilitas 90 hari — " not in text


def test_negative_news_lists_titles_or_ai_summaries_under_the_indicator():
    doc = golden("ANTM")

    plain = "\n".join(render_card(doc))
    ai = "\n".join(
        render_card(
            doc, news={"berita_1": "Analis menilai saham nikel masih tertekan."}
        )
    )

    line = next(ln for ln in plain.splitlines() if "<b>Berita negatif</b>:" in ln)
    after = plain.splitlines()[plain.splitlines().index(line) + 1]
    assert after.startswith('   • 23 September 2026: <a href="https://investasi.kontan')
    assert "Analyst highlights nickel stock recommendations" in after
    assert "Analis menilai saham nikel masih tertekan.</a>" in ai
    assert "Analyst highlights nickel" not in ai
    assert plain.count("   • ") == 4


def test_negative_news_list_is_capped_and_only_links_web_urls():
    doc = copy.deepcopy(golden("BMRI"))
    doc["context"]["negative_news"][0]["source"] = "javascript:alert(1)"

    text = "\n".join(render_card(doc))

    assert text.count("   • ") == 6
    assert "   • dan 3 berita lain" in text
    assert "javascript:" not in text
