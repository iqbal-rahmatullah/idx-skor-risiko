import json
from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from bot.db import get_snapshot, save_snapshot
from bot.sectors.client import SectorsClient
from bot.snapshot.models import (
    Bar,
    Broker,
    Events,
    Financials,
    Holder,
    Overview,
    Ownership,
    Price,
    Source,
    TickerSnapshot,
    Valuation,
)
from bot.tickers import valid_ticker

REPORT_SECTIONS = "overview,ownership,financials,valuation"
N_QUARTERS = 2
INSIDER_WINDOW = timedelta(days=90)
NEWS_WINDOW = timedelta(days=30)
SUSPENSION_WINDOW = timedelta(days=90)
FILING_PERCENT_FIELDS = (
    "share_percentage_before",
    "share_percentage_after",
    "share_percentage_transaction",
)
DAILY_WINDOW = timedelta(days=90)


def strip_jk(symbol: str) -> str:
    return symbol.removesuffix(".JK")


def by_year(rows: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return sorted(
        ({**r, "year": int(r["year"])} for r in rows or []), key=lambda r: r["year"]
    )


def event_date(row: dict[str, Any]) -> str:
    return next((row[k] for k in ("ex_date", "agm_date") if row.get(k)), "")


def by_event_date(rows: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return sorted(
        rows or [], key=lambda r: (event_date(r), json.dumps(r, sort_keys=True))
    )


def since(timestamp: str, as_of: date, window: timedelta) -> bool:
    # Tanpa batas atas: suspensi dan berita sesudah penutupan justru yang dicari putaran 06.00.
    return date.fromisoformat(timestamp[:10]) >= as_of - window


def merge(*parts: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for part in parts:
        for key, value in part.items():
            if key in out:
                raise ValueError(f"Nama field bentrok: {key}")
            out[key] = value
    return out


def flatten(groups: dict[str, Any]) -> dict[str, Any]:
    return merge(*(group or {} for group in groups.values()))


async def fetch_eod(client: SectorsClient, symbol: str, as_of: date) -> dict[str, Any]:
    start = as_of - DAILY_WINDOW
    daily = await client.get(
        f"/daily/{symbol}/",
        missing_ok=True,
        start=start.isoformat(),
        end=as_of.isoformat(),
    )
    corporate_actions = await client.get(
        f"/company/corporate-actions/{symbol}/", missing_ok=True
    )
    quarterly = await client.get(
        f"/financials/quarterly/{symbol}/", missing_ok=True, n_quarters=N_QUARTERS
    )
    broker = await client.get(
        f"/broker-summary/{symbol}/top/",
        missing_ok=True,
        start=as_of.isoformat(),
        end=as_of.isoformat(),
        n_brokers=10,
    )
    return {
        "daily": daily or [],
        "corporate_actions": corporate_actions or {"corporate_actions": {}},
        "quarterly": quarterly or [],
        "composition": await fetch_composition(client, symbol, as_of),
        "broker": broker
        or {"end": as_of.isoformat(), "top_buyers": [], "top_sellers": []},
    }


async def fetch_events(
    client: SectorsClient, symbol: str, as_of: date
) -> dict[str, Any]:
    return {
        "filings": await client.get_all_pages(
            "/filings/",
            missing_ok=True,
            symbol=symbol,
            holder_type="insider",
            start=(as_of - INSIDER_WINDOW).isoformat(),
        ),
        "news": await client.get_all_pages(
            "/news/",
            missing_ok=True,
            symbols=symbol,
            start=(as_of - NEWS_WINDOW).isoformat(),
        ),
        "suspensions": await client.get_all_pages(
            "/suspensions/",
            missing_ok=True,
            symbol=symbol,
            start=(as_of - SUSPENSION_WINDOW).isoformat(),
        ),
    }


async def fetch_composition(
    client: SectorsClient, symbol: str, as_of: date
) -> list[dict[str, Any]]:
    path = f"/company/shareholders-composition/{symbol}/"
    rows = ((await client.get(path, missing_ok=True, year=as_of.year)) or {}).get(
        "data"
    ) or []
    if len(rows) < 2:
        # Awal tahun: bulan pembanding ada di tahun sebelumnya.
        previous = await client.get(path, missing_ok=True, year=as_of.year - 1)
        rows += (previous or {}).get("data") or []
    return rows


async def take_snapshot(
    client: SectorsClient, session: Session, text: str
) -> tuple[TickerSnapshot, bool]:
    symbol = valid_ticker(text)
    if symbol is None:
        raise ValueError(f"Ticker tidak dikenal: {text}")

    client = client.with_new_log()
    report = await client.get(f"/company/report/{symbol}/", sections=REPORT_SECTIONS)
    as_of = date.fromisoformat(report["overview"]["latest_close_date"])
    events = await fetch_events(client, symbol, as_of)

    if cached := get_snapshot(session, symbol, as_of):
        snap = refresh_events(cached, events, client.log)
    else:
        eod = await fetch_eod(client, symbol, as_of)
        snap = normalize({"report": report, **eod, **events}, client.log)
    save_snapshot(session, snap)
    return snap, cached is not None


def refresh_events(
    snap: TickerSnapshot, raw: dict[str, Any], sources: list[dict[str, Any]]
) -> TickerSnapshot:
    fresh = {s["endpoint"] for s in sources}
    return snap.model_copy(
        update={
            "ownership": snap.ownership.model_copy(
                update={
                    "insider_filings": normalize_insider_filings(
                        raw["filings"], snap.as_of
                    )
                }
            ),
            "events": snap.events.model_copy(
                update={
                    "news": normalize_news(snap.symbol, raw["news"], snap.as_of),
                    "suspensions": normalize_suspensions(
                        snap.symbol, raw["suspensions"], snap.as_of
                    ),
                }
            ),
            "sources": [s for s in snap.sources if s.endpoint not in fresh]
            + [Source(**s) for s in sources],
        }
    )


def normalize(raw: dict[str, Any], sources: list[dict[str, Any]]) -> TickerSnapshot:
    report = raw["report"]
    ov = report["overview"]
    as_of = date.fromisoformat(ov["latest_close_date"])
    val = report["valuation"]
    ownership = normalize_ownership(
        report["ownership"], raw["composition"], raw["filings"], as_of
    )
    return TickerSnapshot(
        symbol=strip_jk(report["symbol"]),
        as_of=as_of,
        sector=ov["sector"],
        sub_sector=ov["sub_sector"],
        listing_board=ov["listing_board"],
        overview=Overview(
            company_name=report["company_name"],
            market_cap=ov["market_cap"],
            last_close_price=ov["last_close_price"],
            daily_close_change=ov["daily_close_change"],
            tags=ov["tags"] or [],
            indices=ov["indices"] or [],
            free_float=free_float(ownership.holders),
        ),
        valuation=Valuation(
            forward_pe=val["forward_pe"],
            intrinsic_value=val["intrinsic_value"],
            history=by_year(val["historical_valuation"]),
        ),
        price=normalize_price(raw["daily"], raw["corporate_actions"], as_of),
        financials=normalize_financials(report["financials"], raw["quarterly"]),
        ownership=ownership,
        broker=normalize_broker(raw["broker"]),
        events=normalize_events(
            strip_jk(report["symbol"]),
            raw["news"],
            raw["suspensions"],
            raw["corporate_actions"],
            as_of,
        ),
        sources=sources,
    )


def normalize_price(
    daily: list[dict[str, Any]], corporate_actions: dict[str, Any], as_of: date
) -> Price:
    start = as_of - DAILY_WINDOW
    by_date = {}
    for row in daily:
        day = date.fromisoformat(row["date"])
        if start <= day <= as_of:
            by_date[day] = Bar(**{**row, "date": day})
    return Price(
        bars=[by_date[d] for d in sorted(by_date)],
        splits=by_event_date(
            (corporate_actions["corporate_actions"] or {}).get("stock_split")
        ),
    )


def normalize_financials(
    financials: dict[str, Any], quarterly: list[dict[str, Any]]
) -> Financials:
    ratios = [
        {**flatten({k: v for k, v in r.items() if k != "year"}), "year": r["year"]}
        for r in financials["historical_financial_ratio"] or []
    ]
    return Financials(
        eps=financials["eps"],
        annual=by_year(financials["historical_financials"]),
        annual_ratios=by_year(ratios),
        quarterly=sorted(
            (normalize_quarter(q) for q in quarterly), key=lambda q: q["date"]
        ),
    )


def normalize_quarter(quarter: dict[str, Any]) -> dict[str, Any]:
    q = {
        k: v
        for k, v in quarter.items()
        if k not in ("symbol", "financials_sector_metrics")
    }
    if "total_current_asset" in q:
        q["current_assets"] = q.pop("total_current_asset")
    return merge(q, quarter.get("financials_sector_metrics") or {})


def normalize_holders(major: list[dict[str, Any]] | None) -> list[Holder]:
    return [
        Holder(
            name=h["name"],
            share=None
            if h["share_percentage"] is None
            else float(h["share_percentage"]),
        )
        for h in major or []
    ]


def free_float(holders: list[Holder]) -> float | None:
    return next((h.share for h in holders if h.name == "Public"), None)


def normalize_ownership(
    ownership: dict[str, Any],
    composition: list[dict[str, Any]],
    filings: list[dict[str, Any]],
    as_of: date,
) -> Ownership:
    by_date = {row["date"]: row for row in composition}
    return Ownership(
        holders=normalize_holders(ownership["major_shareholders"]),
        composition=[by_date[d] for d in sorted(by_date)],
        insider_filings=normalize_insider_filings(filings, as_of),
    )


def normalize_insider_filings(
    filings: list[dict[str, Any]], as_of: date
) -> list[dict[str, Any]]:
    insiders = [
        normalize_filing(f)
        for f in filings
        if f["holder_type"] == "insider"
        and since(f["timestamp"], as_of, INSIDER_WINDOW)
    ]
    return sorted(insiders, key=lambda f: f["timestamp"])


def normalize_filing(filing: dict[str, Any]) -> dict[str, Any]:
    out = {
        k: v for k, v in filing.items() if k not in ("symbol", "sector", "sub_sector")
    }
    for field in FILING_PERCENT_FIELDS:
        if out.get(field) is not None:
            out[field] = out[field] / 100
    return out


def normalize_broker(body: dict[str, Any]) -> Broker:
    return Broker(
        date=body["end"],
        top_buyers=sorted(body["top_buyers"] or [], key=lambda b: b["rank"]),
        top_sellers=sorted(body["top_sellers"] or [], key=lambda b: b["rank"]),
    )


def normalize_corporate_actions(
    body: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    return {
        kind: by_event_date(rows)
        for kind, rows in sorted((body["corporate_actions"] or {}).items())
    }


def normalize_events(
    symbol: str,
    news: list[dict[str, Any]],
    suspensions: list[dict[str, Any]],
    corporate_actions: dict[str, Any],
    as_of: date,
) -> Events:
    return Events(
        news=normalize_news(symbol, news, as_of),
        suspensions=normalize_suspensions(symbol, suspensions, as_of),
        corporate_actions=normalize_corporate_actions(corporate_actions),
    )


def normalize_news(
    symbol: str, news: list[dict[str, Any]], as_of: date
) -> list[dict[str, Any]]:
    articles = [
        {**a, "symbols": [strip_jk(s) for s in a["symbols"] or []]}
        for a in news
        if f"{symbol}.JK" in (a["symbols"] or [])
        and since(a["timestamp"], as_of, NEWS_WINDOW)
    ]
    return sorted(articles, key=lambda a: a["timestamp"])


def normalize_suspensions(
    symbol: str, suspensions: list[dict[str, Any]], as_of: date
) -> list[dict[str, Any]]:
    halts = [
        {k: v for k, v in s.items() if k != "symbol"}
        for s in suspensions
        if s["symbol"] == f"{symbol}.JK"
        and since(s["suspension_date"], as_of, SUSPENSION_WINDOW)
    ]
    return sorted(halts, key=lambda s: s["suspension_date"])
