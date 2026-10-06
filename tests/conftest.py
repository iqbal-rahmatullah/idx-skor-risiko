from pathlib import Path

import pytest

FROZEN_IDX = Path(__file__).parent / "fixtures" / "idx"


@pytest.fixture(autouse=True)
def frozen_idx_lists(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("bot.idx.lists.DATA_DIR", FROZEN_IDX)
