import re
from functools import cache
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[2] / "skills" / "analisis-risiko-saham"
TERM_LINE = re.compile(r"^- `([a-z0-9_]+)` — (.+)$")


@cache
def glossary() -> dict[str, str]:
    text = (SKILL_DIR / "references" / "kamus-istilah.md").read_text()
    return {m[1]: m[2] for line in text.splitlines() if (m := TERM_LINE.match(line))}
