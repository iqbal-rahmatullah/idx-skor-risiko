from pathlib import Path

from bot.idx import lists
from bot.risk.build_json import build_indicators, dumps
from tests.conftest import FROZEN_IDX
from tests.test_pillars import TEST_SYMBOLS, full_snapshot

GOLDEN = Path(__file__).resolve().parents[1] / "tests" / "golden"


def main() -> None:
    lists.DATA_DIR = FROZEN_IDX
    for symbol in TEST_SYMBOLS:
        doc = build_indicators(full_snapshot(symbol))
        (GOLDEN / f"indicators_{symbol}.json").write_text(dumps(doc))
        print(f"indicators_{symbol}.json")


if __name__ == "__main__":
    main()
