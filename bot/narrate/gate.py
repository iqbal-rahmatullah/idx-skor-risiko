import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

NUMBER = re.compile(
    r"(Rp\s?)?(\d+(?:[.,]\d+)*)(?:\s?(%|×|x\b|persen\b))?(?:\s?(ribu|juta|miliar|triliun)\b)?",
    re.IGNORECASE,
)
THOUSANDS = re.compile(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?")
PLAIN = re.compile(r"\d+(?:,\d+)?")
SENTENCE_BREAK = re.compile(r"(?<=[.!?])(?<!Tbk\.)(?<!dkk\.)(?<!No\.)(?<!vs\.)\s+")
ADVICE = re.compile(
    r"https?://|www\.|\bt\.me/|\bwa\.me/|(?<![\w.])@\w{3,}"
    r"|\b(?:layak|sebaiknya|segera|saatnya|waktunya|disarankan|ayo|yuk)\s+(?:di)?"
    r"(?:beli|jual|borong|tahan|masuk|keluar|lepas|koleksi|akumulasi)\b"
    r"|\b(?:borong|serok|cuan|target harga|buy|sell|hold)\b"
    r"|(?<!bukan )\brekomendasi (?:beli|jual)\b",
    re.IGNORECASE,
)
UNTRACEABLE_KEYS = frozenset({"title", "excerpt"})
MAX_CHARS = {"summary": 300, "verdicts": 300, "explanations": 300, "news": 250}


def parse(token: str) -> Decimal | None:
    if THOUSANDS.fullmatch(token) or PLAIN.fullmatch(token):
        return Decimal(token.replace(".", "").replace(",", "."))
    return None


Number = tuple[str, Decimal | None]


def unit_of(rp: str, symbol: str, scale: str) -> str:
    if scale:
        return scale.lower()
    if symbol:
        return "%" if symbol.lower() in ("%", "persen") else "×"
    return "Rp" if rp else ""


def numbers_in(text: str) -> list[Number]:
    return [
        (unit_of(rp, symbol, scale), parse(token))
        for rp, token, symbol, scale in NUMBER.findall(text)
    ]


def traceable_numbers(doc: Any) -> set[Number]:
    found: set[Number] = set()
    stack: list[tuple[str | None, Any]] = [(None, doc)]
    while stack:
        key, node = stack.pop()
        if key in UNTRACEABLE_KEYS:
            continue
        if isinstance(node, dict):
            stack.extend(node.items())
        elif isinstance(node, list):
            stack.extend((key, item) for item in node)
        elif isinstance(node, bool) or node is None:
            continue
        elif isinstance(node, int | float):
            found.add(("", abs(Decimal(repr(node)))))
        elif isinstance(node, str) and not node.startswith("http"):
            found.update(n for n in numbers_in(node) if n[1] is not None)
    return found


@dataclass
class Checked:
    summary: str | None = None
    verdicts: dict[str, str] = field(default_factory=dict)
    explanations: dict[str, str] = field(default_factory=dict)
    news: dict[str, str] = field(default_factory=dict)
    dropped: list[str] = field(default_factory=list)


def check(narration: dict[str, Any], doc: dict[str, Any]) -> Checked:
    allowed = traceable_numbers(doc)
    plain = {value for _, value in allowed}
    result = Checked()

    def traceable(unit: str, value: Decimal | None) -> bool:
        return value in plain if unit == "" else (unit, value) in allowed

    def keep(text: object, limit: int) -> str | None:
        if not isinstance(text, str):
            return None
        kept: list[str] = []
        full = False
        for sentence in SENTENCE_BREAK.split(text.strip()):
            full = full or len(" ".join([*kept, sentence])) > limit
            if (
                not full
                and not ADVICE.search(sentence)
                and all(traceable(*n) for n in numbers_in(sentence))
            ):
                kept.append(sentence)
            else:
                result.dropped.append(sentence)
        return " ".join(kept) or None

    def keep_all(raw: object, known: set[str], limit: int) -> dict[str, str]:
        items = raw.items() if isinstance(raw, dict) else []
        return {k: text for k, v in items if k in known and (text := keep(v, limit))}

    result.summary = keep(narration.get("summary"), MAX_CHARS["summary"])
    result.verdicts = keep_all(
        narration.get("verdicts"),
        {p["id"] for p in doc["pillars"]},
        MAX_CHARS["verdicts"],
    )
    result.explanations = keep_all(
        narration.get("explanations"),
        {i["id"] for p in doc["pillars"] for i in p["indicators"]},
        MAX_CHARS["explanations"],
    )
    result.news = keep_all(
        narration.get("news"),
        {n["id"] for n in doc.get("context", {}).get("negative_news", [])},
        MAX_CHARS["news"],
    )
    return result
