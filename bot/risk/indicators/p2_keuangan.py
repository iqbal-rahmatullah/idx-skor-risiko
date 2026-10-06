from datetime import date
from typing import Any

from bot.risk import thresholds as t
from bot.risk.format import day, idr, num, pct
from bot.risk.indicators.common import (
    is_financial,
    no_peers,
    not_applicable,
    peer_metric,
    unavailable,
)
from bot.risk.models import Indicator, make_indicator
from bot.snapshot.models import TickerSnapshot

PILLAR = "kesehatan_keuangan"


def latest(rows: list[dict[str, Any]], field: str) -> dict[str, Any] | None:
    return next((r for r in reversed(rows) if r.get(field) is not None), None)


def annual_row(
    rows: list[dict[str, Any]], field: str, year: int | None = None
) -> dict[str, Any] | None:
    if year is not None:
        row = next(
            (r for r in rows if r.get("year") == year and r.get(field) is not None),
            None,
        )
        if row is not None:
            return row
    return latest(rows, field)


def peer_year(snap: TickerSnapshot, metric: str) -> int | None:
    return snap.peers.years.get(metric) if snap.peers else None


def period(row: dict[str, Any]) -> str:
    return str(row.get("date") or row["year"])


def period_label(row: dict[str, Any]) -> str:
    return day(date.fromisoformat(row["date"])) if row.get("date") else str(row["year"])


def negative_equity(snap: TickerSnapshot) -> Indicator | None:
    if is_financial(snap):
        return None
    fin = snap.financials
    row, source = latest(fin.quarterly, "total_equity"), "quarterly"
    if row is None:
        row, source = latest(fin.annual, "total_equity"), "annual"
    if row is None:
        status, value, display = "tidak_tersedia", None, "tidak tersedia"
        path = "financials.quarterly"
    else:
        value = row["total_equity"]
        status = "bermasalah" if value < 0 else "wajar"
        display = f"{idr(value)} ({period_label(row)})"
        path = f"financials.{source}[{period(row)}].total_equity"
    return make_indicator(
        t.I_X_EQUITY,
        id="negative_equity",
        pillar=PILLAR,
        label="Ekuitas negatif",
        status=status,
        value=value,
        display=display,
        threshold="ekuitas < 0: bermasalah",
        weight=3,
        evidence_path=path,
    )


def no_revenue(snap: TickerSnapshot) -> Indicator | None:
    if is_financial(snap):
        return None
    fin = snap.financials
    source = "quarterly" if latest(fin.quarterly, "revenue") else "annual"
    rows = [r for r in getattr(fin, source) if r.get("revenue") is not None]
    if not rows:
        status, value, display = "tidak_tersedia", None, "tidak tersedia"
        path = "financials.quarterly"
    else:
        last = rows[-1]
        value = last["revenue"]
        unchanged = len(rows) > 1 and rows[-2]["revenue"] == value
        status = "bermasalah" if value == 0 or unchanged else "wajar"
        display = f"{idr(value)} ({period_label(last)})"
        if unchanged:
            display += f", sama dengan {period_label(rows[-2])}"
        path = f"financials.{source}[{period(last)}].revenue"
    return make_indicator(
        t.I_X_REVENUE,
        id="no_revenue",
        pillar=PILLAR,
        label="Tanpa pendapatan usaha",
        status=status,
        value=value,
        display=display,
        threshold="pendapatan nol atau tidak berubah dari laporan sebelumnya: bermasalah",
        weight=3,
        evidence_path=path,
    )


def car(snap: TickerSnapshot) -> Indicator | None:
    if not is_financial(snap):
        return None
    row = latest(snap.financials.annual_ratios, "capital_adequacy_ratio")
    if row is None:
        status, value, display = "tidak_tersedia", None, "tidak tersedia"
        path = "financials.annual_ratios"
    else:
        value = row["capital_adequacy_ratio"]
        if value < t.CAR_MIN:
            status = "bermasalah"
        elif value <= t.CAR_MAX_REQUIREMENT:
            status = "perhatian"
        else:
            status = "kuat"
        display = f"{pct(value)} ({period_label(row)})"
        path = f"financials.annual_ratios[{period(row)}].capital_adequacy_ratio"
    return make_indicator(
        t.POJK_KPMM,
        id="car",
        pillar=PILLAR,
        label="Rasio kecukupan modal (CAR)",
        status=status,
        value=value,
        display=display,
        threshold=(
            f"< {pct(t.CAR_MIN)} bermasalah · {pct(t.CAR_MIN)}–{pct(t.CAR_MAX_REQUIREMENT)}"
            f" perhatian · > {pct(t.CAR_MAX_REQUIREMENT)} kuat"
        ),
        weight=3,
        evidence_path=path,
        note="buffer konservasi 2,5% untuk KBMI 3–4 belum diperhitungkan",
    )


def ldr_rim(snap: TickerSnapshot) -> Indicator | None:
    if not is_financial(snap):
        return None
    row = latest(snap.financials.annual_ratios, "loan_to_deposit_ratio")
    note = "LDR dipakai sebagai proksi RIM; RIM juga memperhitungkan surat berharga"
    if row is None:
        status, value, display = "tidak_tersedia", None, "tidak tersedia"
        path = "financials.annual_ratios"
    else:
        value = row["loan_to_deposit_ratio"]
        status = "bermasalah" if value > t.RIM_UPPER else "wajar"
        display = f"{pct(value)} ({period_label(row)})"
        path = f"financials.annual_ratios[{period(row)}].loan_to_deposit_ratio"
        if value < t.RIM_LOWER:
            note += (
                f". Di bawah batas bawah RIM {pct(t.RIM_LOWER)}: likuiditas longgar,"
                " bukan risiko bagi investor"
            )
    return make_indicator(
        t.PADG_RIM,
        id="ldr_rim",
        pillar=PILLAR,
        label="Rasio kredit terhadap dana (proksi RIM)",
        status=status,
        value=value,
        display=display,
        threshold=f"> {pct(t.RIM_UPPER)} bermasalah",
        weight=2,
        evidence_path=path,
        note=note,
    )


def debt_to_equity(snap: TickerSnapshot) -> Indicator | None:
    if is_financial(snap):
        return None
    fields = {
        "id": "debt_to_equity",
        "pillar": PILLAR,
        "label": "Liabilitas terhadap ekuitas",
        "threshold": "> persentil 75 subsektor",
        "weight": 1,
    }
    row = annual_row(
        snap.financials.annual_ratios,
        "debt_to_equity_ratio",
        peer_year(snap, "debt_to_equity"),
    )
    if row is None:
        return unavailable(
            t.DEBT_TO_EQUITY, evidence_path="financials.annual_ratios", **fields
        )
    value = row["debt_to_equity_ratio"]
    display = f"{num(value)}× ({row['year']})"
    path = f"financials.annual_ratios[{row['year']}].debt_to_equity_ratio"
    if value < 0:
        return not_applicable(
            t.DEBT_TO_EQUITY,
            "ekuitas negatif; lihat indikator Ekuitas negatif",
            value=value,
            display=display,
            evidence_path=path,
            **fields,
        )
    peers = peer_metric(snap, "debt_to_equity")
    if peers is None:
        return unavailable(
            t.DEBT_TO_EQUITY, no_peers(snap), evidence_path=path, **fields
        )
    return make_indicator(
        t.DEBT_TO_EQUITY,
        status="bermasalah" if value > peers.p75 else "wajar",
        value=value,
        display=f"{display}; persentil 75 subsektor: {num(peers.p75)}×",
        evidence_path=path,
        **fields,
    )


ALTMAN_FIELDS = (
    "current_assets",
    "current_liabilities",
    "total_assets",
    "retained_earnings",
    "ebit",
    "total_equity",
    "total_liabilities",
)


def altman_z(snap: TickerSnapshot) -> Indicator:
    fields = {
        "id": "altman_z",
        "pillar": PILLAR,
        "label": "Skor Altman Z''",
        "threshold": (
            f"< {num(t.ALTMAN_DISTRESS)} bermasalah · {num(t.ALTMAN_DISTRESS)}–"
            f"{num(t.ALTMAN_SAFE)} perhatian · > {num(t.ALTMAN_SAFE)} kuat"
        ),
        "weight": 2,
        "evidence_path": "financials.annual",
    }
    if is_financial(snap):
        return not_applicable(
            t.ALTMAN, "model Altman tidak cocok untuk neraca lembaga keuangan", **fields
        )
    row = next(
        (
            r
            for r in reversed(snap.financials.annual)
            if all(r.get(f) is not None for f in ALTMAN_FIELDS)
            and r["total_assets"]
            and r["total_liabilities"]
        ),
        None,
    )
    if row is None:
        return unavailable(t.ALTMAN, **fields)
    assets = row["total_assets"]
    ratios = (
        (row["current_assets"] - row["current_liabilities"]) / assets,
        row["retained_earnings"] / assets,
        row["ebit"] / assets,
        row["total_equity"] / row["total_liabilities"],
    )
    z = sum(c * x for c, x in zip(t.ALTMAN_COEFFICIENTS, ratios, strict=True))
    if z < t.ALTMAN_DISTRESS:
        status = "bermasalah"
    elif z <= t.ALTMAN_SAFE:
        status = "perhatian"
    else:
        status = "kuat"
    return make_indicator(
        t.ALTMAN,
        status=status,
        value=z,
        display=f"{num(z)} ({row['year']})",
        **{**fields, "evidence_path": f"financials.annual[{row['year']}]"},
    )


PIOTROSKI_FIELDS = (
    "earnings",
    "total_assets",
    "operating_cash_flow",
    "long_term_debt",
    "current_assets",
    "current_liabilities",
    "outstanding_shares",
    "gross_profit",
    "revenue",
)


def piotroski_score(rows: list[dict[str, Any]]) -> tuple[int, int | None, list[str]]:
    by_year = {r["year"]: r for r in rows}
    reported = [y for y, r in by_year.items() if r.get("earnings") is not None]
    if not reported:
        return 0, None, ["earnings"]
    y0 = max(reported)
    y1, y2 = y0 - 1, y0 - 2
    needed = {
        y0: PIOTROSKI_FIELDS,
        y1: PIOTROSKI_FIELDS,
        y2: ("earnings", "total_assets"),
    }
    missing = [
        f"{field} {year}"
        for year, names in needed.items()
        for field in names
        if by_year.get(year, {}).get(field) is None
    ]
    if missing:
        return y0, None, missing
    a, b, c = by_year[y0], by_year[y1], by_year[y2]
    divisors = (
        b["total_assets"],
        c["total_assets"],
        a["current_liabilities"],
        b["current_liabilities"],
        a["revenue"],
        b["revenue"],
    )
    if not all(divisors):
        return y0, None, ["pembagi bernilai nol"]
    roa, roa_prev = a["earnings"] / b["total_assets"], b["earnings"] / c["total_assets"]
    cfo = a["operating_cash_flow"] / b["total_assets"]
    leverage = a["long_term_debt"] / ((a["total_assets"] + b["total_assets"]) / 2)
    leverage_prev = b["long_term_debt"] / ((b["total_assets"] + c["total_assets"]) / 2)
    checks = (
        roa > 0,
        cfo > 0,
        roa > roa_prev,
        cfo > roa,
        leverage < leverage_prev,
        a["current_assets"] / a["current_liabilities"]
        > b["current_assets"] / b["current_liabilities"],
        a["outstanding_shares"] <= b["outstanding_shares"],
        a["gross_profit"] / a["revenue"] > b["gross_profit"] / b["revenue"],
        a["revenue"] / b["total_assets"] > b["revenue"] / c["total_assets"],
    )
    return y0, sum(checks), []


def piotroski_f(snap: TickerSnapshot) -> Indicator:
    fields = {
        "id": "piotroski_f",
        "pillar": PILLAR,
        "label": "Skor Piotroski",
        "threshold": (
            f"≤ {t.PIOTROSKI_WEAK} bermasalah · ≥ {t.PIOTROSKI_STRONG} kuat, dari 9 cek"
        ),
        "weight": 2,
        "evidence_path": "financials.annual",
    }
    if is_financial(snap):
        return not_applicable(
            t.PIOTROSKI, "cek Piotroski tidak cocok untuk lembaga keuangan", **fields
        )
    year, score, missing = piotroski_score(snap.financials.annual)
    if score is None:
        shown = ", ".join(missing[:3]) + (" dan lainnya" if len(missing) > 3 else "")
        return unavailable(t.PIOTROSKI, f"data tidak lengkap: {shown}", **fields)
    if score <= t.PIOTROSKI_WEAK:
        status = "bermasalah"
    elif score >= t.PIOTROSKI_STRONG:
        status = "kuat"
    else:
        status = "wajar"
    return make_indicator(
        t.PIOTROSKI,
        status=status,
        value=score,
        display=f"{score}/9 ({year} dibanding {year - 1})",
        **fields,
    )


def npl_proxy(snap: TickerSnapshot) -> Indicator | None:
    if not is_financial(snap):
        return None
    note = "proksi pencadangan, bukan NPL; tidak dibandingkan dengan ambang NPL 5%"
    fields = {
        "id": "npl_proxy",
        "pillar": PILLAR,
        "label": "Proksi cadangan kredit bermasalah",
        "threshold": "> persentil 75 bank lain",
        "weight": 1,
    }
    year = peer_year(snap, "npl_proxy")
    rows = [
        r
        for r in snap.financials.annual
        if r.get("allowance_for_loans") is not None and r.get("gross_loan")
    ]
    row = next((r for r in rows if r["year"] == year), rows[-1] if rows else None)
    if row is None:
        return unavailable(
            t.NPL_PROXY, note, evidence_path="financials.annual", **fields
        )
    value = abs(row["allowance_for_loans"]) / row["gross_loan"]
    path = f"financials.annual[{row['year']}].allowance_for_loans"
    peers = peer_metric(snap, "npl_proxy")
    if peers is None:
        return unavailable(t.NPL_PROXY, no_peers(snap), evidence_path=path, **fields)
    return make_indicator(
        t.NPL_PROXY,
        status="bermasalah" if value > peers.p75 else "wajar",
        value=value,
        display=f"{pct(value)} ({row['year']}); persentil 75 bank: {pct(peers.p75)}",
        evidence_path=path,
        note=note,
        **fields,
    )


def cost_to_income(snap: TickerSnapshot) -> Indicator | None:
    if not is_financial(snap):
        return None
    note = "proksi efisiensi dari Sectors, bukan BOPO resmi"
    fields = {
        "id": "cost_to_income",
        "pillar": PILLAR,
        "label": "Biaya terhadap pendapatan (proksi BOPO)",
        "threshold": "> persentil 75 bank lain",
        "weight": 1,
    }
    row = annual_row(
        snap.financials.annual_ratios,
        "cost_to_income_ratio",
        peer_year(snap, "cost_to_income"),
    )
    if row is None:
        return unavailable(
            t.COST_TO_INCOME, note, evidence_path="financials.annual_ratios", **fields
        )
    value = row["cost_to_income_ratio"]
    path = f"financials.annual_ratios[{row['year']}].cost_to_income_ratio"
    display = f"{num(value)} ({row['year']})"
    if value < 0:
        return not_applicable(
            t.COST_TO_INCOME,
            "rasio negatif karena pendapatan negatif; tidak bisa dibandingkan",
            value=value,
            display=display,
            evidence_path=path,
            **fields,
        )
    peers = peer_metric(snap, "cost_to_income")
    if peers is None:
        return unavailable(
            t.COST_TO_INCOME, no_peers(snap), evidence_path=path, **fields
        )
    return make_indicator(
        t.COST_TO_INCOME,
        status="bermasalah" if value > peers.p75 else "wajar",
        value=value,
        display=f"{display}; persentil 75 bank: {num(peers.p75)}",
        evidence_path=path,
        note=note,
        **fields,
    )


def nim(snap: TickerSnapshot) -> Indicator | None:
    if not is_financial(snap):
        return None
    fields = {
        "id": "nim",
        "pillar": PILLAR,
        "label": "Margin bunga bersih (NIM)",
        "threshold": "< persentil 25 bank lain",
        "weight": 1,
    }
    row = annual_row(
        snap.financials.annual_ratios, "net_interest_margin", peer_year(snap, "nim")
    )
    if row is None:
        return unavailable(t.NIM, evidence_path="financials.annual_ratios", **fields)
    value = row["net_interest_margin"]
    path = f"financials.annual_ratios[{row['year']}].net_interest_margin"
    peers = peer_metric(snap, "nim")
    if peers is None:
        return unavailable(t.NIM, no_peers(snap), evidence_path=path, **fields)
    return make_indicator(
        t.NIM,
        status="bermasalah" if value < peers.p25 else "wajar",
        value=value,
        display=f"{pct(value)} ({row['year']}); persentil 25 bank: {pct(peers.p25)}",
        evidence_path=path,
        **fields,
    )
