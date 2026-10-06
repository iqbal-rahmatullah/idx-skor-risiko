from decimal import ROUND_HALF_UP, Decimal

from bot.risk.models import Indicator

ASSESSABLE = frozenset({"kuat", "wajar", "perhatian", "bermasalah"})
GRADES = ((20, "A"), (40, "B"), (60, "C"), (80, "D"), (100, "E"))


def round_half_up(x: float) -> int:
    return int(Decimal(repr(x)).quantize(Decimal(1), ROUND_HALF_UP))


def pillar_score(indicators: list[Indicator]) -> float | None:
    assessable = [i for i in indicators if i.status in ASSESSABLE]
    total = sum(i.weight for i in assessable)
    if not total:
        return None
    flagged = sum(
        i.weight
        for i in assessable
        if i.status == "bermasalah" and i.dismissed_reason is None
    )
    return 100 * flagged / total


def final_score(
    pillar_scores: list[float | None], weights: list[float] | None = None
) -> int | None:
    weights = weights or [1] * len(pillar_scores)
    pairs = [
        (s, w) for s, w in zip(pillar_scores, weights, strict=True) if s is not None
    ]
    if not pairs:
        return None
    return round_half_up(sum(s * w for s, w in pairs) / sum(w for _, w in pairs))


def grade(score: int | None) -> str | None:
    if score is None:
        return None
    return next(letter for upper, letter in GRADES if score <= upper)
