import json
from decimal import Decimal
from pathlib import Path

import pytest

from bot.narrate.gate import check, numbers_in, traceable_numbers

GOLDEN = Path(__file__).parent / "golden"
EXAMPLES = Path(__file__).parents[1] / "skills/analisis-risiko-saham/references/contoh"


def golden(symbol: str) -> dict:
    return json.loads((GOLDEN / f"indicators_{symbol}.json").read_text())


def narration(summary: str, **explanations: str) -> dict:
    return {"summary": summary, "verdicts": {}, "explanations": explanations}


@pytest.mark.parametrize(
    "text",
    [
        "Free float ANTM 36%.",
        "Harga naik 47% dalam sepekan.",
        "PER ANTM 12,5× di atas rata-rata.",
        "Nilai transaksi Rp320 miliar per hari.",
        "Target harga Rp4.500 dalam 3 bulan ke depan.",
        "Skor ini setara 88 poin.",
        "Laba naik 0.44 kali lipat.",
        "Data per 31 Juni 2027.",
    ],
)
def test_fabricated_numbers_are_dropped(text):
    result = check(narration(text), golden("ANTM"))

    assert result.summary is None
    assert result.dropped == [text]


@pytest.mark.parametrize(
    "text",
    [
        "Free float ANTM 35%, di atas ambang 15%.",
        "Porsinya 0,35 dari seluruh saham.",
        "Nilai transaksi Rp320,42 miliar per hari selama 63 hari bursa.",
        "Laporan terakhir per 30 Juni 2026 mencatat ekuitas Rp38,53 triliun.",
        "Skor risiko 7 dari 0–100, grade A.",
        "Harga Rp3.170 masih di bawah Graham Number Rp3.206,22.",
        "Rasio liabilitasnya 0,44× pada 2025.",
        "Harga turun 2,16% pada hari bursa terakhir.",
        "Tidak ada angka di kalimat ini.",
    ],
)
def test_traceable_numbers_pass(text):
    result = check(narration(text), golden("ANTM"))

    assert result.summary == text
    assert result.dropped == []


def test_only_offending_sentences_are_dropped():
    text = "PBV ANTM 2,04× di atas rata-rata 1,36×. Harga bisa naik 20% lagi. Tidak ada suspensi."

    result = check(narration(text), golden("ANTM"))

    assert (
        result.summary == "PBV ANTM 2,04× di atas rata-rata 1,36×. Tidak ada suspensi."
    )
    assert result.dropped == ["Harga bisa naik 20% lagi."]


def test_unknown_keys_and_non_text_are_discarded():
    raw = {
        "summary": 42,
        "verdicts": {"valuasi": "PBV lebih mahal dari sejenis.", "palsu": "x"},
        "explanations": {"pb_vs_peer": "PBV 2,04×.", "bukan_indikator": "y"},
    }

    result = check(raw, golden("ANTM"))

    assert result.summary is None
    assert result.verdicts == {"valuasi": "PBV lebih mahal dari sejenis."}
    assert result.explanations == {"pb_vs_peer": "PBV 2,04×."}


def test_abbreviation_does_not_split_sentence():
    text = "Aneka Tambang Tbk. mencatat free float 35%."

    assert check(narration(text), golden("ANTM")).summary == text


def test_number_parsing_follows_indonesian_format():
    assert numbers_in("Rp1.234,5 dan 7,5% serta 10.000 lembar, 0,44×") == [
        ("Rp", 1234.5),
        ("%", 7.5),
        ("", 10000),
        ("×", Decimal("0.44")),
    ]
    assert numbers_in("0.44") == [("", None)]


def test_traceable_numbers_ignore_sign():
    assert ("%", Decimal("2.16")) in traceable_numbers(golden("ANTM"))


def test_unit_must_match_but_plain_numbers_match_any_unit():
    doc = golden("ANTM")

    assert check(narration("Butuh 20 hari bursa."), doc).dropped == []
    assert check(narration("Naik 20% sepekan."), doc).dropped == ["Naik 20% sepekan."]
    assert check(narration("Free float 35 persen."), doc).dropped == []


@pytest.mark.parametrize("path", sorted(EXAMPLES.glob("*.json")), ids=lambda p: p.stem)
def test_skill_examples_pass_their_own_gate(path):
    example = json.loads(path.read_text())

    result = check(example, golden(path.stem))

    assert result.dropped == []


def test_news_summaries_are_gated_and_keyed_by_context_ids():
    raw = {
        "summary": None,
        "verdicts": {},
        "explanations": {},
        "news": {
            "berita_1": "Analis menilai saham nikel masih tertekan aturan RKAB dan HPM.",
            "berita_2": "Saham nikel anjlok 11,7% sejak awal tahun.",
            "berita_9": "Berita yang tidak ada.",
        },
    }

    result = check(raw, golden("ANTM"))

    assert result.news == {
        "berita_1": "Analis menilai saham nikel masih tertekan aturan RKAB dan HPM."
    }
    assert result.dropped == ["Saham nikel anjlok 11,7% sejak awal tahun."]


@pytest.mark.parametrize(
    ("symbol", "text"),
    [
        ("ANTM", "PER ANTM 12,5x di atas rata-rata."),
        ("ANTM", "Harga bisa naik 20 persen sepekan."),
        ("ANTM", "Ekuitas ANTM Rp38,53 juta."),
        ("BMRI", "Asing menjual bersih BMRI Rp798 miliar."),
    ],
)
def test_word_units_scale_and_news_numbers_are_not_loopholes(symbol, text):
    assert check(narration(text), golden(symbol)).dropped == [text]


@pytest.mark.parametrize(
    "text",
    [
        "Saham ini layak dibeli sekarang.",
        "Sebaiknya segera jual sebelum turun lagi.",
        "Analis memasang target harga yang tinggi.",
        "Gabung grup t.me/pompomsinyal untuk sinyal harian.",
        "Hubungi @admin_sinyal untuk info lebih lanjut.",
        "Cek https://contoh.id untuk rekomendasi beli.",
    ],
)
def test_advice_links_and_handles_are_dropped(text):
    assert check(narration(text), golden("ANTM")).dropped == [text]


@pytest.mark.parametrize(
    "text",
    [
        "Bukan rekomendasi beli atau jual.",
        "Di papan ini jual-beli bisa lebih sulit.",
        "Investor asing menjual bersih saham ANTM di awal pekan.",
        "Ekuitas ANTM Rp38,53 triliun per 30 Juni 2026.",
        "Free float 35 persen.",
    ],
)
def test_plain_descriptions_still_pass(text):
    assert check(narration(text), golden("ANTM")).dropped == []


def test_overlong_text_is_trimmed_at_sentence_boundaries():
    first = "Tidak ada suspensi sejak 24 Juni 2026."
    raw = {"summary": " ".join([first] * 20), "verdicts": {}, "explanations": {}}

    result = check(raw, golden("ANTM"))

    assert len(result.summary) <= 300
    assert result.summary.startswith(first)
    assert result.dropped
