from datetime import date
from typing import Any

from pydantic import BaseModel

Row = dict[str, Any]


class Source(BaseModel):
    endpoint: str
    fetched_at: str
    credits: int | None


class Overview(BaseModel):
    company_name: str
    market_cap: int | None
    last_close_price: float | None
    daily_close_change: float | None
    tags: list[str]
    indices: list[str]
    free_float: float | None


class Bar(BaseModel):
    date: date
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: int | None


class Price(BaseModel):
    bars: list[Bar]
    splits: list[Row]


class Holder(BaseModel):
    name: str
    share: float | None


class Ownership(BaseModel):
    holders: list[Holder]
    composition: list[Row]
    insider_filings: list[Row]


class Broker(BaseModel):
    date: date
    top_buyers: list[Row]
    top_sellers: list[Row]


class Events(BaseModel):
    news: list[Row]
    suspensions: list[Row]
    corporate_actions: dict[str, list[Row]]


class Financials(BaseModel):
    eps: float | None
    annual: list[Row]
    annual_ratios: list[Row]
    quarterly: list[Row]


class Valuation(BaseModel):
    forward_pe: float | None
    intrinsic_value: float | None
    history: list[Row]


class TickerSnapshot(BaseModel):
    symbol: str
    as_of: date
    sector: str
    sub_sector: str
    listing_board: str
    overview: Overview
    valuation: Valuation
    price: Price
    financials: Financials
    ownership: Ownership
    broker: Broker
    events: Events
    sources: list[Source]
