import json
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import Text, UniqueConstraint, create_engine, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from bot.snapshot.models import Bar, Broker, PeerStats, TickerSnapshot


class Base(DeclarativeBase):
    pass


class SnapshotRow(Base):
    __tablename__ = "ticker_snapshots"
    __table_args__ = (UniqueConstraint("symbol", "as_of"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str]
    as_of: Mapped[date]
    data: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))


class Registration(Base):
    __tablename__ = "registrations"
    __table_args__ = (UniqueConstraint("user_id", "symbol"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int]
    chat_id: Mapped[int]
    symbol: Mapped[str]
    thread_id: Mapped[int | None]
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
    closed_at: Mapped[datetime | None]


class UserRound(Base):
    __tablename__ = "user_rounds"

    user_id: Mapped[int] = mapped_column(primary_key=True)
    last_round_at: Mapped[datetime]


class RiskDocRow(Base):
    __tablename__ = "risk_docs"
    __table_args__ = (UniqueConstraint("symbol", "as_of"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str]
    as_of: Mapped[date]
    data: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))


class PeerStatsRow(Base):
    __tablename__ = "peer_stats"
    __table_args__ = (UniqueConstraint("sub_sector", "as_of"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    sub_sector: Mapped[str]
    as_of: Mapped[date]
    data: Mapped[str] = mapped_column(Text)


class BrokerDayRow(Base):
    __tablename__ = "broker_days"
    __table_args__ = (UniqueConstraint("symbol", "day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str]
    day: Mapped[date]
    data: Mapped[str] = mapped_column(Text)


class PriceBarRow(Base):
    __tablename__ = "price_bars"
    __table_args__ = (UniqueConstraint("symbol", "day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str]
    day: Mapped[date]
    open: Mapped[float | None]
    high: Mapped[float | None]
    low: Mapped[float | None]
    close: Mapped[float | None]
    volume: Mapped[int | None]


class AlertedEvent(Base):
    __tablename__ = "alerted_events"
    __table_args__ = (UniqueConstraint("user_id", "symbol", "key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int]
    symbol: Mapped[str]
    key: Mapped[str]
    alerted_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))


class RoundRow(Base):
    __tablename__ = "rounds"

    eod: Mapped[date] = mapped_column(primary_key=True)
    finished_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))


def as_utc(moment: datetime) -> datetime:
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment


def make_session_factory(url: str) -> sessionmaker[Session]:
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    return sessionmaker(engine)


def save_snapshot(session: Session, snap: TickerSnapshot) -> None:
    stmt = insert(SnapshotRow).values(
        symbol=snap.symbol,
        as_of=snap.as_of,
        data=snap.model_dump_json(),
        created_at=datetime.now(UTC),
    )
    session.execute(
        stmt.on_conflict_do_update(
            index_elements=["symbol", "as_of"],
            set_={"data": stmt.excluded.data, "created_at": stmt.excluded.created_at},
        )
    )
    session.commit()


def get_snapshot(session: Session, symbol: str, as_of: date) -> TickerSnapshot | None:
    data = session.scalar(
        select(SnapshotRow.data).where(
            SnapshotRow.symbol == symbol, SnapshotRow.as_of == as_of
        )
    )
    return TickerSnapshot.model_validate_json(data) if data else None


def latest_snapshot(session: Session, symbol: str) -> TickerSnapshot | None:
    data = session.scalar(
        select(SnapshotRow.data)
        .where(SnapshotRow.symbol == symbol)
        .order_by(SnapshotRow.as_of.desc())
        .limit(1)
    )
    return TickerSnapshot.model_validate_json(data) if data else None


def get_registration(
    session: Session, user_id: int, symbol: str
) -> Registration | None:
    return session.scalar(
        select(Registration).where(
            Registration.user_id == user_id, Registration.symbol == symbol
        )
    )


def upsert_registration(
    session: Session, *, user_id: int, chat_id: int, symbol: str, thread_id: int | None
) -> Registration:
    reg = get_registration(session, user_id, symbol)
    if reg is None:
        reg = Registration(user_id=user_id, chat_id=chat_id, symbol=symbol)
        session.add(reg)
    reg.chat_id, reg.thread_id, reg.active, reg.closed_at = (
        chat_id,
        thread_id,
        True,
        None,
    )
    session.commit()
    return reg


def deactivate(session: Session, *, user_id: int, symbol: str) -> None:
    reg = get_registration(session, user_id, symbol)
    if reg is not None:
        reg.active, reg.closed_at = False, datetime.now(UTC)
        session.commit()


def active_registrations(
    session: Session, user_id: int | None = None
) -> list[Registration]:
    query = select(Registration).where(Registration.active.is_(True))
    if user_id is not None:
        query = query.where(Registration.user_id == user_id)
    return list(
        session.scalars(query.order_by(Registration.user_id, Registration.symbol))
    )


def save_risk_doc(session: Session, doc: dict[str, Any]) -> None:
    stmt = insert(RiskDocRow).values(
        symbol=doc["symbol"],
        as_of=date.fromisoformat(doc["as_of"]),
        data=json.dumps(doc, ensure_ascii=False),
        created_at=datetime.now(UTC),
    )
    session.execute(
        stmt.on_conflict_do_update(
            index_elements=["symbol", "as_of"],
            set_={"data": stmt.excluded.data, "created_at": stmt.excluded.created_at},
        )
    )
    session.commit()


def latest_risk_docs(
    session: Session, symbol: str, n: int, before: date | None = None
) -> list[dict[str, Any]]:
    query = select(RiskDocRow.data).where(RiskDocRow.symbol == symbol)
    if before is not None:
        query = query.where(RiskDocRow.as_of < before)
    rows = session.scalars(query.order_by(RiskDocRow.as_of.desc()).limit(n))
    return [json.loads(r) for r in rows]


def get_last_round(session: Session, user_id: int) -> datetime | None:
    row = session.get(UserRound, user_id)
    return as_utc(row.last_round_at) if row else None


def set_last_round(session: Session, user_id: int, moment: datetime) -> None:
    row = session.get(UserRound, user_id)
    if row is None:
        session.add(UserRound(user_id=user_id, last_round_at=moment))
    else:
        row.last_round_at = moment
    session.commit()


def save_peer_stats(session: Session, stats: PeerStats) -> None:
    stmt = insert(PeerStatsRow).values(
        sub_sector=stats.sub_sector, as_of=stats.as_of, data=stats.model_dump_json()
    )
    session.execute(
        stmt.on_conflict_do_update(
            index_elements=["sub_sector", "as_of"], set_={"data": stmt.excluded.data}
        )
    )
    session.commit()


def latest_peer_stats(
    session: Session, sub_sector: str, on_or_before: date
) -> PeerStats | None:
    data = session.scalar(
        select(PeerStatsRow.data)
        .where(
            PeerStatsRow.sub_sector == sub_sector, PeerStatsRow.as_of <= on_or_before
        )
        .order_by(PeerStatsRow.as_of.desc())
        .limit(1)
    )
    return PeerStats.model_validate_json(data) if data else None


def save_broker_day(
    session: Session, symbol: str, day: date, body: dict[str, Any]
) -> None:
    stmt = insert(BrokerDayRow).values(
        symbol=symbol, day=day, data=json.dumps(body, ensure_ascii=False)
    )
    session.execute(
        stmt.on_conflict_do_update(
            index_elements=["symbol", "day"], set_={"data": stmt.excluded.data}
        )
    )
    session.commit()


def broker_history(
    session: Session, symbol: str, before: date, since: date | None = None
) -> list[Broker]:
    query = select(BrokerDayRow.data).where(
        BrokerDayRow.symbol == symbol, BrokerDayRow.day < before
    )
    if since is not None:
        query = query.where(BrokerDayRow.day >= since)
    rows = session.scalars(query.order_by(BrokerDayRow.day))
    return [Broker.from_api(json.loads(r)) for r in rows]


def save_price_bars(session: Session, symbol: str, bars: list[Bar]) -> None:
    for bar in bars:
        values = bar.model_dump()
        stmt = insert(PriceBarRow).values(
            symbol=symbol, day=values.pop("date"), **values
        )
        session.execute(
            stmt.on_conflict_do_update(
                index_elements=["symbol", "day"],
                set_={k: stmt.excluded[k] for k in values},
            )
        )
    session.commit()


def price_bars(session: Session, symbol: str, start: date, end: date) -> list[Bar]:
    rows = session.scalars(
        select(PriceBarRow)
        .where(
            PriceBarRow.symbol == symbol,
            PriceBarRow.day >= start,
            PriceBarRow.day <= end,
        )
        .order_by(PriceBarRow.day)
    )
    return [
        Bar(
            date=r.day,
            open=r.open,
            high=r.high,
            low=r.low,
            close=r.close,
            volume=r.volume,
        )
        for r in rows
    ]


def alerted_keys(session: Session, user_id: int, symbol: str) -> set[str]:
    return set(
        session.scalars(
            select(AlertedEvent.key).where(
                AlertedEvent.user_id == user_id, AlertedEvent.symbol == symbol
            )
        )
    )


def mark_alerted(session: Session, user_id: int, symbol: str, keys: list[str]) -> None:
    for key in keys:
        session.execute(
            insert(AlertedEvent)
            .values(
                user_id=user_id, symbol=symbol, key=key, alerted_at=datetime.now(UTC)
            )
            .on_conflict_do_nothing()
        )
    session.commit()


def last_eod(session: Session) -> date | None:
    return session.scalar(select(RoundRow.eod).order_by(RoundRow.eod.desc()).limit(1))


def mark_eod(session: Session, eod: date) -> None:
    session.execute(
        insert(RoundRow)
        .values(eod=eod, finished_at=datetime.now(UTC))
        .on_conflict_do_nothing()
    )
    session.commit()
