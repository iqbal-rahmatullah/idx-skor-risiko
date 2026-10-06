import csv
import os
import re
from datetime import date
from pathlib import Path
from typing import Any

import certifi
import httpx

from bot.idx import lists

NOTATION_API = (
    "https://www.idx.id/primary/ListedCompany/GetSpecialNotation?start=0&length=1000"
)
NOTATION_PAGE = "https://www.idx.id/id/perusahaan-tercatat/notasi-khusus/"
FIELDS = ("kode", "notasi", "tanggal_data", "sumber_url", "keterangan")
CODE = re.compile(r"[A-Z]{4}")
NOTATIONS = re.compile(r"[A-Z](?:,[A-Z])*")
MIN_KEPT_SHARE = 0.5


def to_row(raw: dict[str, Any]) -> dict[str, str]:
    try:
        code, notation = raw["EmitenCode"], raw["Notation"]
        day = date.fromisoformat(raw["Date"][:10])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"baris notasi tidak valid: {raw!r:.120}") from exc
    if not (CODE.fullmatch(code or "") and NOTATIONS.fullmatch(notation or "")):
        raise ValueError(f"baris notasi tidak valid: {raw!r:.120}")
    return {
        "kode": code,
        "notasi": notation,
        "tanggal_data": day.isoformat(),
        "sumber_url": NOTATION_PAGE,
        "keterangan": (raw.get("Description") or "").strip(),
    }


async def refresh_notations(
    path: Path | None = None, transport: httpx.AsyncBaseTransport | None = None
) -> int:
    async with httpx.AsyncClient(
        verify=certifi.where(), timeout=30, transport=transport
    ) as client:
        response = await client.get(NOTATION_API)
        response.raise_for_status()
    rows = sorted(map(to_row, response.json()["Results"]), key=lambda r: r["kode"])
    path = path or lists.DATA_DIR / lists.NOTATION_FILE
    old = lists.read_rows(path) or []
    if len(rows) < max(1, len(old) * MIN_KEPT_SHARE):
        raise ValueError(f"daftar notasi menyusut dari {len(old)} ke {len(rows)} baris")
    staging = path.with_suffix(".tmp")
    with staging.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(staging, path)
    return len(rows)
