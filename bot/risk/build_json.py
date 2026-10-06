import json
from collections.abc import Callable
from typing import Any

from bot.risk.dismiss import apply_dismissals
from bot.risk.indicators.p1_ukuran import (
    broker_concentration,
    daily_liquidity,
    free_float,
    relative_liquidity,
    sub_51_price,
    volume_spike,
)
from bot.risk.indicators.p2_keuangan import (
    altman_z,
    car,
    cost_to_income,
    debt_to_equity,
    ldr_rim,
    negative_equity,
    nim,
    no_revenue,
    npl_proxy,
    piotroski_f,
)
from bot.risk.indicators.p3_valuasi import graham_number, pb_vs_peer, pe_vs_peer
from bot.risk.indicators.p4_kepemilikan import (
    insider_buying,
    insider_selling,
    retail_share_shift,
    shareholder_concentration,
)
from bot.risk.indicators.p5_harga import (
    ara_arb_frequency,
    drawdown_90d,
    unexplained_move,
    volatility_90d,
)
from bot.risk.indicators.p6_peristiwa import (
    accrual_ratio,
    dilution_event,
    negative_news,
    negative_news_context,
    special_monitoring_board,
    special_notation,
    suspension_uma,
)
from bot.risk.models import STATUSES, Indicator
from bot.risk.score import final_score, grade, pillar_score, round_half_up
from bot.risk.thresholds import PILLAR_WEIGHTS
from bot.snapshot.models import TickerSnapshot

PILLARS = (
    ("ukuran_likuiditas", "Ukuran dan likuiditas"),
    ("kesehatan_keuangan", "Kesehatan keuangan"),
    ("valuasi", "Valuasi"),
    ("kepemilikan", "Kepemilikan dan orang dalam"),
    ("perilaku_harga", "Perilaku harga"),
    ("peristiwa", "Peristiwa dan berita"),
)

INDICATORS: tuple[Callable[[TickerSnapshot], Indicator | None], ...] = (
    free_float,
    daily_liquidity,
    sub_51_price,
    volume_spike,
    broker_concentration,
    relative_liquidity,
    negative_equity,
    no_revenue,
    debt_to_equity,
    altman_z,
    piotroski_f,
    car,
    npl_proxy,
    ldr_rim,
    cost_to_income,
    nim,
    pe_vs_peer,
    pb_vs_peer,
    graham_number,
    insider_selling,
    insider_buying,
    shareholder_concentration,
    retail_share_shift,
    ara_arb_frequency,
    volatility_90d,
    drawdown_90d,
    unexplained_move,
    special_notation,
    special_monitoring_board,
    suspension_uma,
    negative_news,
    dilution_event,
    accrual_ratio,
)


def build_indicators(snap: TickerSnapshot, trigger: str = "risk") -> dict[str, Any]:
    indicators = apply_dismissals(
        snap, [ind for fn in INDICATORS if (ind := fn(snap)) is not None]
    )
    counted = [i for i in indicators if i.dismissed_reason is None]
    pillars, scores = [], []
    for pillar_id, label in PILLARS:
        members = [i for i in indicators if i.pillar == pillar_id]
        score = pillar_score(members)
        scores.append(score)
        pillars.append(
            {
                "id": pillar_id,
                "label": label,
                "score": None if score is None else round_half_up(score),
                "indicators": [i.model_dump(mode="json") for i in members],
            }
        )
    total = final_score(scores, [PILLAR_WEIGHTS[p] for p, _ in PILLARS])
    return {
        "symbol": snap.symbol,
        "company_name": snap.overview.company_name,
        "as_of": snap.as_of.isoformat(),
        "trigger": trigger,
        "score": {"value": total, "grade": grade(total), "scale": "0–100"},
        "summary_counts": {s: sum(i.status == s for i in counted) for s in STATUSES},
        "pillars": pillars,
        "dismissed": [
            {
                "id": i.id,
                "label": i.label,
                "display": i.display,
                "reason": i.dismissed_reason,
            }
            for i in indicators
            if i.dismissed_reason is not None
        ],
        "unavailable": [i.id for i in indicators if i.status == "tidak_tersedia"],
        "context": {"negative_news": negative_news_context(snap)},
    }


def dumps(doc: dict[str, Any]) -> str:
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
