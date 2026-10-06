import csv
from datetime import date
from pathlib import Path
from typing import Any

from bot.snapshot.models import IdxLists

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "idx"
NOTATION_FILE = "notasi_khusus.csv"
HSC_FILE = "hsc.csv"
HSC_PAGE = (
    "https://www.idx.id/id/perusahaan-tercatat/kepemilikan-saham-terkonsentrasi-tinggi/"
)


def read_rows(path: Path) -> list[dict[str, str]] | None:
    if not path.exists():
        return None
    with path.open(newline="") as f:
        return list(csv.DictReader(f)) or None


def notation_rows() -> list[dict[str, str]] | None:
    return read_rows(DATA_DIR / NOTATION_FILE)


def idx_lists_for(
    symbol: str, notation_path: Path | None = None, hsc_path: Path | None = None
) -> IdxLists | None:
    notation_rows = read_rows(notation_path or DATA_DIR / NOTATION_FILE)
    hsc_rows = read_rows(hsc_path or DATA_DIR / HSC_FILE)
    if notation_rows is None and hsc_rows is None:
        return None
    fields: dict[str, Any] = {}
    if notation_rows:
        row = next((r for r in notation_rows if r["kode"] == symbol), None)
        fields |= {
            "notations": [n for n in (row["notasi"] if row else "").split(",") if n],
            "as_of": max(date.fromisoformat(r["tanggal_data"]) for r in notation_rows),
            "source_url": notation_rows[0]["sumber_url"],
            "description": (row["keterangan"] or None) if row else None,
        }
    if hsc_rows:
        events = sorted(
            (r for r in hsc_rows if r["kode"] == symbol), key=lambda r: r["tanggal"]
        )
        fields |= {
            "hsc": bool(events) and events[-1]["peristiwa"] == "pengenaan",
            "hsc_as_of": max(date.fromisoformat(r["tanggal_data"]) for r in hsc_rows),
            "hsc_source_url": events[-1]["sumber_url"] if events else HSC_PAGE,
        }
    return IdxLists(**fields)
