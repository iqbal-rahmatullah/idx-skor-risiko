from datetime import date
from typing import Literal

from pydantic import BaseModel

from bot.risk.thresholds import Rule, SourceType

Status = Literal[
    "kuat", "wajar", "perhatian", "bermasalah", "tidak_tersedia", "tidak_berlaku"
]
STATUSES: tuple[Status, ...] = (
    "kuat",
    "wajar",
    "perhatian",
    "bermasalah",
    "tidak_tersedia",
    "tidak_berlaku",
)


class Indicator(BaseModel):
    id: str
    pillar: str
    label: str
    status: Status
    is_new: bool | None = None
    since: date | None = None
    value: int | float | str | None
    display: str
    threshold: str
    source: str
    source_type: SourceType
    source_url: str
    effective: date
    weight: int
    evidence_path: str
    note: str | None = None


def make_indicator(rule: Rule, **fields: object) -> Indicator:
    return Indicator(
        source=rule.source,
        source_type=rule.source_type,
        source_url=rule.url,
        effective=rule.effective,
        **fields,
    )
