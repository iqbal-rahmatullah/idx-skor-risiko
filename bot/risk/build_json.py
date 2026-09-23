import json
from collections.abc import Callable
from typing import Any

from bot.risk.indicators.p1_ukuran import daily_liquidity, free_float, sub_51_price
from bot.risk.indicators.p2_keuangan import car, ldr_rim, negative_equity, no_revenue
from bot.risk.indicators.p6_peristiwa import (
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

# Urutan di sini menentukan urutan di indicators.json; None berarti indikator tidak relevan untuk sektornya.
INDICATORS: tuple[Callable[[TickerSnapshot], Indicator | None], ...] = (
    free_float,
    daily_liquidity,
    sub_51_price,
    negative_equity,
    no_revenue,
    car,
    ldr_rim,
    special_notation,
    special_monitoring_board,
    suspension_uma,
)


def build_indicators(snap: TickerSnapshot, trigger: str = "risk") -> dict[str, Any]:
    indicators = [ind for fn in INDICATORS if (ind := fn(snap)) is not None]
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
        "as_of": snap.as_of.isoformat(),
        "trigger": trigger,
        "score": {"value": total, "grade": grade(total)},
        "summary_counts": {s: sum(i.status == s for i in indicators) for s in STATUSES},
        "pillars": pillars,
        "dismissed": [],
        "unavailable": [i.id for i in indicators if i.status == "tidak_tersedia"],
    }


def dumps(doc: dict[str, Any]) -> str:
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
