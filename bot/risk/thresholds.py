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
    "https://market.bisnis.com/read/20260401/7/1963525/bei-resmi-berlakukan-free-float-15-big-caps-diberi-tenggat-waktu-hingga-2027",
)
I_V = Rule(
    "Peraturan BEI I-V (Papan Akselerasi)",
    "regulator",
    date(2026, 3, 31),
    "https://www.investasiku.id/eduvest/saham/free-float-saham",
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
BIG_CAP_TRANSITION_END = date(2028, 3, 31)
SMALL_CAP_TRANSITION_END = date(2029, 3, 31)
BOARDS_WITH_CAP_TRANSITION = frozenset({"Main", "Development"})

LIQUIDITY_MAX_VALUE_IDR = 5_000_000
LIQUIDITY_MAX_VOLUME = 10_000
PRICE_MIN_IDR = 51
DIVIDEND_EXEMPTION_YEARS = 1

FINANCIAL_SECTOR = "Financials"
# Minimum KPMM: 8% untuk profil risiko 1, sampai 11–14% untuk profil risiko 4–5.
CAR_MIN = 0.08
CAR_MAX_REQUIREMENT = 0.14
RIM_LOWER = 0.84
RIM_UPPER = 0.94
SUSPENSION_WINDOW_DAYS = 90

MONITORING_BOARD_NOTATION = "X"
# Arti huruf dari keterangan resmi di daftar notasi khusus BEI (idx.id, 22 Sep 2026).
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
