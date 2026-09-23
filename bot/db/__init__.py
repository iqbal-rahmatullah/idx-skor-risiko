from datetime import UTC, date, datetime

from sqlalchemy import Text, UniqueConstraint, create_engine, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from bot.snapshot.models import TickerSnapshot


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
