import asyncio

from bot.demo import LABEL, play


def test_demo_plays_two_moments_offline():
    texts = asyncio.run(play())

    assert len(texts) == 2
    assert all(LABEL in t for t in texts)
    cash = next(t for t in texts if "<b>CASH</b>" in t)
    bbri = next(t for t in texts if "<b>BBRI</b>" in t)
    assert "grade B ke C" in cash
    assert "Baru bermasalah: Lonjakan harga tanpa katalis" in cash
    assert "Bendera yang dibatalkan" not in cash
    assert "Penyebab wajar: ex-date dividen pada 23 September 2026." in bbri
