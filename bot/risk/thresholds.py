from dataclasses import dataclass, replace
from datetime import date
from typing import Literal

SourceType = Literal["regulator", "akademik", "data"]


@dataclass(frozen=True)
class Rule:
    source: str
    source_type: SourceType
    effective: date
    url: str


I_A = Rule(
    "Peraturan BEI I-A dan SE-00004/BEI/03-2026",
    "regulator",
    date(2026, 3, 31),
    "https://www.idx.id/id/berita/siaran-pers/2589",
)
I_V = Rule(
    "Peraturan BEI I-V (Kep-00104/BEI/07-2023) V.1.1",
    "regulator",
    date(2023, 7, 31),
    "https://web.archive.org/web/20250529133641/https://gopublic.idx.co.id/media/1445/peraturan-i-v-pencatatan-saham-di-papan-akselerasi-3.pdf",
)

I_X = Rule(
    "Peraturan BEI I-X (Kep-00035/BEI/06-2025)",
    "regulator",
    date(2025, 6, 4),
    "https://www.idx.id/Media/pyuil405/signed_peraturan_i_x_penempatan_pencatatan_ebe_pada_papan_pemantauan_khusus.pdf",
)
I_X_LIQUIDITY = replace(I_X, source=f"{I_X.source} III.1.7 dan III.3")
I_X_PRICE = replace(I_X, source=f"{I_X.source} III.1.1, III.2, dan III.3")
I_X_EQUITY = replace(I_X, source=f"{I_X.source} III.1.5")
I_X_REVENUE = replace(I_X, source=f"{I_X.source} III.1.3")
POJK_KPMM = Rule(
    "POJK 11/POJK.03/2016 Pasal 2 ayat (3) jo. POJK 27/POJK.03/2022",
    "regulator",
    date(2016, 2, 2),
    "https://peraturan.bpk.go.id/Download/135028/POJK%20Nomor%2011%20Tahun%202016.pdf",
)
SUSPENSION = Rule(
    "Suspensi oleh BEI (Peraturan II-A); jendela 90 hari pilihan tim (PRD §10)",
    "regulator",
    date(2026, 9, 22),
    "https://www.idx.co.id/id/peraturan/peraturan-bursa/",
)
I_X_BOARD = replace(I_X, source=f"{I_X.source} II.4; daftar notasi khusus BEI")
IDX_NOTATION = Rule(
    "Daftar notasi khusus BEI",
    "regulator",
    date(2025, 6, 4),
    "https://www.idx.id/id/perusahaan-tercatat/notasi-khusus/",
)
PADG_RIM = Rule(
    "PADG No. 23 Tahun 2025 Pasal 7 jo. PADG No. 18 Tahun 2026",
    "regulator",
    date(2025, 10, 20),
    "https://www.bi.go.id/id/publikasi/peraturan/Pages/PADG_232025.aspx",
)

SECTORS_DOCS = "https://docs.sectors.app/get-started/v2/overview"
DAILY_DOCS = "https://docs.sectors.app/api-references/v2/indonesia/transaction/daily"
SCREENER_DOCS = (
    "https://docs.sectors.app/api-references/v2/indonesia/screener/companies"
)
BROKER_DOCS = (
    "https://docs.sectors.app/api-references/v2/indonesia/brokers/broker-summary-top"
)
TEAM_CHOICE = date(2026, 9, 23)


def team_choice(source: str, url: str = SECTORS_DOCS) -> Rule:
    return Rule(source, "data", TEAM_CHOICE, url)


VOLUME_SPIKE = team_choice(
    "Persentil 95 volume 90 hari saham itu (pilihan tim)", DAILY_DOCS
)
BROKER_CONCENTRATION = team_choice(
    "Persentil 95 riwayat broker saham itu, minimal 20 hari bursa (pilihan tim);"
    " HHI KPPU hanya analogi",
    BROKER_DOCS,
)
RELATIVE_LIQUIDITY = team_choice(
    "Persentil 10 nilai transaksi anggota subsektor yang aktif (pilihan tim)",
    DAILY_DOCS,
)
DEBT_TO_EQUITY = team_choice(
    "Persentil 75 subsektor, field debt_to_equity_ratio Sectors (pilihan tim)",
    SCREENER_DOCS,
)
NPL_PROXY = team_choice(
    "Persentil 75 bank lain, cadangan kerugian kredit ÷ kredit (proksi;"
    " definisi NPL di POJK 40/POJK.03/2019)",
    SCREENER_DOCS,
)
COST_TO_INCOME = team_choice(
    "Persentil 75 bank lain, cost_to_income_ratio Sectors (proksi, bukan BOPO)",
    SCREENER_DOCS,
)
NIM = team_choice(
    "Persentil 25 bank lain, net_interest_margin Sectors (pilihan tim)",
    SCREENER_DOCS,
)
PE_PEER = team_choice("pe_peer_avg Sectors; PER 15 Graham hanya rujukan")
PB_PEER = team_choice("pb_peer_avg Sectors")
RETAIL_SHIFT = team_choice(
    "Persentil 90 perubahan porsi ritel anggota subsektor (pilihan tim)"
)
ARA_ARB = team_choice(
    "Persentil 95 subsektor (pilihan tim); batas harian Kep-00002 dan"
    " Kep-00003/BEI/04-2025, 10% untuk Papan Akselerasi dan Pemantauan Khusus"
    " (sumber sekunder)",
    "https://www.cnbcindonesia.com/market/20250408084106-17-624101/bei-ubah-kebijakan-arb-ini-aturan-terbarunya",
)
VOLATILITY = team_choice(
    "Persentil 90 RSD harga anggota subsektor (pilihan tim)", DAILY_DOCS
)
DRAWDOWN = team_choice(
    "Persentil 90 drawdown anggota subsektor (pilihan tim)", DAILY_DOCS
)
UNEXPLAINED_MOVE = team_choice(
    "Persentil 95 return harian 90 hari saham itu (pilihan tim); pembatalan PRD §9",
    DAILY_DOCS,
)
NEGATIVE_NEWS = team_choice(
    "Tag Bearish atau Violation di /news Sectors; minimal 3 dalam 7 hari (pilihan tim)"
)
DILUTION = team_choice(
    "Right issue atau waran di /company/corporate-actions Sectors;"
    " jendela 90 hari (pilihan tim)"
)
ALTMAN = Rule(
    "Altman dkk. (2017), Journal of International Financial Management and"
    " Accounting 28(2): Z'' non-manufaktur dan pasar berkembang",
    "akademik",
    date(2017, 6, 1),
    "https://doi.org/10.1111/jifm.12053",
)
PIOTROSKI = Rule(
    "Piotroski (2000), Journal of Accounting Research 38",
    "akademik",
    date(2000, 1, 1),
    "http://www.chicagobooth.edu/~/media/FE874EE65F624AAEBD0166B1974FD74D.pdf",
)
GRAHAM = Rule(
    "Graham, The Intelligent Investor, bab 14",
    "akademik",
    date(1949, 1, 1),
    "https://stablebread.com/graham-number/",
)
INSIDER = Rule(
    "POJK 4 Tahun 2024 (laporan kepemilikan); Lakonishok & Lee (2001),"
    " Review of Financial Studies 14(1)",
    "akademik",
    date(2001, 1, 1),
    "https://ideas.repec.org/a/oup/rfinst/v14y2001i1p79-111.html",
)
HSC = Rule(
    "Pengumuman Kepemilikan Saham Terkonsentrasi Tinggi BEI",
    "regulator",
    date(2026, 4, 2),
    "https://www.idx.id/id/perusahaan-tercatat/kepemilikan-saham-terkonsentrasi-tinggi/",
)
ACCRUAL = Rule(
    "Sloan (1996), The Accounting Review 71(3); persentil 75 subsektor (pilihan tim)",
    "akademik",
    date(1996, 7, 1),
    "https://publications.aaahq.org/accounting-review/article/71/3/289/18989",
)

PILLAR_WEIGHTS = {
    "ukuran_likuiditas": 1,
    "kesehatan_keuangan": 1,
    "valuasi": 1,
    "kepemilikan": 1,
    "perilaku_harga": 1,
    "peristiwa": 1,
}

FREE_FLOAT_TARGET = 0.15
FREE_FLOAT_BIG_CAP_MILESTONE = 0.125
FREE_FLOAT_ACCELERATION = 0.075
BIG_CAP_MIN_IDR = 5 * 10**12
BIG_CAP_MILESTONE_END = date(2027, 3, 31)
BIG_CAP_TRANSITION_END = date(2028, 3, 31)
SMALL_CAP_TRANSITION_END = date(2029, 3, 31)
BOARDS_WITH_CAP_TRANSITION = frozenset({"Main", "Development"})

LIQUIDITY_MAX_VALUE_IDR = 5_000_000
LIQUIDITY_MAX_VOLUME = 10_000
PRICE_MIN_IDR = 51
DIVIDEND_EXEMPTION_YEARS = 1

FINANCIAL_SECTOR = "Financials"
CAR_MIN = 0.08
CAR_MAX_REQUIREMENT = 0.14
RIM_LOWER = 0.84
RIM_UPPER = 0.94
SUSPENSION_WINDOW_DAYS = 90

MONITORING_BOARD_NOTATION = "X"
NOTATION_MEANINGS = {
    "A": "opini tidak wajar dari akuntan publik",
    "B": "permohonan pailit atau dalam kondisi pailit",
    "C": "perkara hukum yang berdampak material",
    "D": "opini tidak menyatakan pendapat (disclaimer)",
    "E": "ekuitas negatif",
    "F": "sanksi OJK, pelanggaran ringan",
    "G": "sanksi OJK, pelanggaran sedang",
    "I": "tidak menerapkan hak suara multipel di Papan Ekonomi Baru",
    "L": "terlambat menyampaikan laporan keuangan",
    "M": "permohonan PKPU",
    "N": "menerapkan hak suara multipel di luar Papan Ekonomi Baru",
    "S": "tidak ada pendapatan usaha",
    "X": "dicatatkan di Papan Pemantauan Khusus",
    "Y": "belum menyelenggarakan RUPS tahunan",
}
# N dan I hanya menandai struktur hak suara; X dinilai terpisah oleh special_monitoring_board.
NON_PROBLEM_NOTATIONS = frozenset({"N", "I", MONITORING_BOARD_NOTATION})

# Metodologi persentil (PRD §10): tingkat persentil dan ukuran sampel minimum adalah pilihan tim.
PERCENTILE_MIN_SAMPLE = 5
PERCENTILE_LEVELS = (10, 25, 75, 90, 95)

ARA_BANDS = ((200, 0.35), (5000, 0.25), (float("inf"), 0.20))
ARB_REGULAR = 0.15
SPECIAL_BOARD_LIMIT = 0.10
TICK_SIZES = ((200, 1), (500, 2), (2000, 5), (5000, 10), (float("inf"), 25))
LIMIT_TOUCH_DAYS = 10

# "Mayoritas emiten sesubsektor" di aturan pembatalan PRD §9: lebih dari separuh.
SECTOR_MAJORITY = 0.5
# Alert F5: skor bergeser 10 poin atau lebih (PRD §7).
ALERT_SCORE_SHIFT = 10

BROKER_MIN_HISTORY = 20
BROKER_HISTORY_WINDOW_DAYS = 90

ALTMAN_COEFFICIENTS = (6.56, 3.26, 6.72, 1.05)
ALTMAN_DISTRESS = 1.1
ALTMAN_SAFE = 2.6
PIOTROSKI_WEAK = 2
PIOTROSKI_STRONG = 8
GRAHAM_FACTOR = 22.5
INSIDER_WINDOW_DAYS = 30
NEGATIVE_NEWS_MIN = 3
NEGATIVE_NEWS_DAYS = 7
NEGATIVE_NEWS_TAGS = frozenset({"Bearish", "Violation"})
DILUTION_WINDOW_DAYS = 90
