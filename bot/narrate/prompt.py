import json
from functools import cache
from typing import Any

from bot.narrate.skill import SKILL_DIR

REFERENCES = ("kamus-istilah.md", "nada.md", "kombinasi.md")


@cache
def system_prompt() -> str:
    refs = SKILL_DIR / "references"
    parts = [(SKILL_DIR / "SKILL.md").read_text()]
    parts += [(refs / name).read_text() for name in REFERENCES]
    parts += [
        f"# Contoh keluaran untuk {path.stem}\n\n{path.read_text()}"
        for path in sorted((refs / "contoh").glob("*.json"))
    ]
    return "\n\n---\n\n".join(parts)


def build_messages(doc: dict[str, Any]) -> list[dict[str, str]]:
    data = json.dumps(doc, ensure_ascii=False).replace("</", "<\\/")
    return [
        {"role": "system", "content": system_prompt()},
        {
            "role": "user",
            "content": f"<data>\n{data}\n</data>\n\nTulis narasi untuk data di atas sesuai format keluaran.",
        },
    ]
