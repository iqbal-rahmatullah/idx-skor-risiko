import csv
from datetime import date
from pathlib import Path

from bot.snapshot.models import IdxLists

NOTATION_CSV = (
    Path(__file__).resolve().parents[1] / "data" / "idx" / "notasi_khusus.csv"
)


def idx_lists_for(symbol: str, path: Path = NOTATION_CSV) -> IdxLists | None:
    if not path.exists():
        return None
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return None
    row = next((r for r in rows if r["kode"] == symbol), None)
    return IdxLists(
        notations=[n for n in (row["notasi"] if row else "").split(",") if n],
        as_of=max(date.fromisoformat(r["tanggal_data"]) for r in rows),
        source_url=rows[0]["sumber_url"],
        description=(row["keterangan"] or None) if row else None,
    )
