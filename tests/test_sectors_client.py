import asyncio

import httpx
import pytest

from bot.sectors.client import (
    FIXTURES_DIR,
    SectorsClient,
    SectorsError,
    fixture_transport,
)


def run(coro):
    return asyncio.run(coro)


def live_client(handler) -> SectorsClient:
    return SectorsClient("kunci-rahasia", transport=httpx.MockTransport(handler))


def test_sends_raw_key_without_bearer_to_v2():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    async def go():
        async with live_client(handler) as client:
            return await client.get("/company/report/ANTM/", sections="overview")

    assert run(go()) == {"ok": True}
    assert seen[0].headers["authorization"] == "kunci-rahasia"
    assert seen[0].url.path == "/v2/company/report/ANTM/"
    assert seen[0].url.params["sections"] == "overview"


def test_logs_credits_from_header():
    def handler(request):
        return httpx.Response(200, json={}, headers={"limit-consumption": "4"})

    async def go():
        async with live_client(handler) as client:
            await client.get("/company/report/ANTM/")
            return client.log

    [entry] = run(go())
    assert entry["endpoint"] == "/company/report/ANTM/"
    assert entry["credits"] == 4
    assert entry["fetched_at"]


def test_credits_none_when_header_missing():
    async def go():
        async with live_client(lambda r: httpx.Response(200, json={})) as client:
            await client.get("/daily/ANTM/")
            return client.log

    assert run(go())[0]["credits"] is None


def test_get_all_pages_follows_next_offset():
    pages = {0: ([1, 2], 2), 2: ([3, 4], 4), 4: ([5], None)}

    def handler(request):
        results, next_offset = pages[int(request.url.params["offset"])]
        return httpx.Response(
            200, json={"results": results, "pagination": {"next_offset": next_offset}}
        )

    async def go():
        async with live_client(handler) as client:
            return await client.get_all_pages("/filings/", symbol="ANTM")

    assert run(go()) == [1, 2, 3, 4, 5]


def test_error_is_typed_and_hides_key():
    def handler(request):
        return httpx.Response(
            401, json={"error": "TOKEN_NOT_VALID", "message": "Given token not valid"}
        )

    async def go():
        async with live_client(handler) as client:
            await client.get("/company/report/ANTM/")

    with pytest.raises(SectorsError) as exc:
        run(go())
    assert exc.value.status == 401
    assert exc.value.code == "TOKEN_NOT_VALID"
    assert "kunci-rahasia" not in str(exc.value)


def offline_client() -> SectorsClient:
    return SectorsClient("kunci-rahasia", transport=fixture_transport(FIXTURES_DIR))


def test_offline_serves_fixture_by_url_path():
    async def go():
        async with offline_client() as client:
            return await client.get("/company/report/ANTM/", sections="overview")

    assert run(go())["symbol"] == "ANTM.JK"


def test_offline_uses_symbol_param_for_list_endpoints():
    async def go():
        async with offline_client() as client:
            return await client.get_all_pages("/filings/", symbol="BBCA")

    assert {row["symbol"] for row in run(go())} == {"BBCA.JK"}


def test_offline_falls_back_to_market_wide_fixture_and_stops_paging():
    async def go():
        async with offline_client() as client:
            return await client.get_all_pages("/news/", symbols="ANTM")

    # news.json berisi satu halaman dengan has_next=true; mock harus menutup paginasi.
    assert len(run(go())) == 20


def test_offline_missing_fixture_fails_without_network():
    async def go():
        async with offline_client() as client:
            await client.get("/daily/BBRI/")

    with pytest.raises(SectorsError, match="fixture belum ada: daily/BBRI"):
        run(go())


def test_get_all_pages_stops_when_offset_does_not_advance():
    def handler(request):
        return httpx.Response(
            200, json={"results": [1], "pagination": {"next_offset": 0}}
        )

    async def go():
        async with live_client(handler) as client:
            await client.get_all_pages("/news/")

    with pytest.raises(SectorsError, match="PAGINATION_STUCK"):
        run(go())


def test_missing_ok_turns_real_404_into_none():
    def handler(request):
        return httpx.Response(404, json={"error": "NOT_FOUND", "message": "no data"})

    async def go():
        async with live_client(handler) as client:
            one = await client.get("/daily/ANTM/", missing_ok=True)
            many = await client.get_all_pages("/news/", missing_ok=True)
            return one, many

    assert run(go()) == (None, [])


def test_missing_ok_still_fails_on_missing_fixture():
    async def go():
        async with offline_client() as client:
            await client.get("/daily/BBRI/", missing_ok=True)

    with pytest.raises(SectorsError, match="fixture belum ada"):
        run(go())
