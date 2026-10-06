import asyncio
import itertools
import time

import httpx
import pytest

from bot.sectors.client import (
    FIXTURES_DIR,
    RecordingTransport,
    SectorsClient,
    SectorsError,
    fixture_candidates,
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

    assert len(run(go())) == 20


def test_offline_missing_fixture_fails_without_network():
    async def go():
        async with offline_client() as client:
            await client.get("/daily/ZZZZ/")

    with pytest.raises(SectorsError, match="fixture belum ada: daily/ZZZZ"):
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
            await client.get("/daily/ZZZZ/", missing_ok=True)

    with pytest.raises(SectorsError, match="fixture belum ada"):
        run(go())


def test_recording_serves_existing_fixture_without_live_call(tmp_path):
    (tmp_path / "daily").mkdir()
    (tmp_path / "daily" / "ANTM.json").write_text('[{"date": "2026-09-22"}]')
    live_calls = []

    def live(request):
        live_calls.append(request)
        return httpx.Response(200, json=[])

    async def go():
        transport = RecordingTransport(tmp_path, live=httpx.MockTransport(live))
        async with SectorsClient("k", transport=transport) as client:
            return await client.get("/daily/ANTM/")

    assert run(go()) == [{"date": "2026-09-22"}]
    assert live_calls == []


def test_recording_fetches_missing_fixture_once_and_saves_it(tmp_path):
    live_calls = []

    def live(request):
        live_calls.append(request.url.path)
        return httpx.Response(
            200, json={"results": [1], "pagination": {"next_offset": None}}
        )

    async def go():
        transport = RecordingTransport(tmp_path, live=httpx.MockTransport(live))
        async with SectorsClient("k", transport=transport) as client:
            first = await client.get("/filings/", symbol="BBCA")
            second = await client.get("/filings/", symbol="BBCA")
        return first, second

    first, second = run(go())
    assert first["results"] == second["results"] == [1]
    assert live_calls == ["/v2/filings/"]
    assert (tmp_path / "filings" / "BBCA.json").exists()


def test_recording_does_not_save_live_errors(tmp_path):
    def live(request):
        return httpx.Response(404, json={"error": "NOT_FOUND", "message": "no data"})

    async def go():
        transport = RecordingTransport(tmp_path, live=httpx.MockTransport(live))
        async with SectorsClient("k", transport=transport) as client:
            return await client.get("/daily/XXXX/", missing_ok=True)

    assert run(go()) is None
    assert not list(tmp_path.rglob("*.json"))


def candidates_for(url: str, **params) -> list[str]:
    return fixture_candidates(httpx.Request("GET", url, params=params))


def test_screener_fixture_key_depends_on_query_but_not_offset():
    a = candidates_for(
        "https://api.sectors.app/v2/companies/", where="x", order_by="-y", offset=0
    )
    b = candidates_for(
        "https://api.sectors.app/v2/companies/", where="x", order_by="-y", offset=200
    )
    c = candidates_for(
        "https://api.sectors.app/v2/companies/", where="x", order_by="-z", offset=0
    )

    assert a == b
    assert a != c
    assert a[0].startswith("companies/")


def test_broker_fixture_key_includes_date():
    assert candidates_for(
        "https://api.sectors.app/v2/broker-summary/ANTM/top/",
        start="2026-09-22",
        end="2026-09-22",
    ) == ["broker-summary/ANTM/top/2026-09-22"]


def test_recording_ignores_market_wide_fallback_for_symbol_queries(tmp_path):
    (tmp_path / "news.json").write_text(
        '{"results": [], "pagination": {"next_offset": null}}'
    )
    live_calls = []

    def live(request):
        live_calls.append(request.url.params["symbols"])
        return httpx.Response(
            200, json={"results": [{"title": "x"}], "pagination": {"next_offset": None}}
        )

    async def go():
        transport = RecordingTransport(tmp_path, live=httpx.MockTransport(live))
        async with SectorsClient("k", transport=transport) as client:
            return await client.get("/news/", symbols="BIKE")

    assert run(go())["results"] == [{"title": "x"}]
    assert live_calls == ["BIKE"]
    assert (tmp_path / "news" / "BIKE.json").exists()


def test_rate_limit_is_retried_then_succeeds():
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(429, json={"error": "RATE_LIMIT_EXCEEDED"})
        return httpx.Response(200, json={"ok": True})

    async def go():
        client = SectorsClient(
            "k", transport=httpx.MockTransport(handler), retry_delays=(0, 0, 0)
        )
        async with client:
            return await client.get("/daily/ANTM/")

    assert run(go()) == {"ok": True}
    assert len(calls) == 3


def test_rate_limit_gives_up_after_retries():
    def handler(request):
        return httpx.Response(
            429, json={"error": "RATE_LIMIT_EXCEEDED", "message": "x"}
        )

    async def go():
        client = SectorsClient(
            "k", transport=httpx.MockTransport(handler), retry_delays=(0, 0)
        )
        async with client:
            await client.get("/daily/ANTM/")

    with pytest.raises(SectorsError) as exc:
        run(go())
    assert exc.value.status == 429


def test_min_interval_spaces_requests_even_across_log_clones():
    stamps = []

    def handler(request):
        stamps.append(time.monotonic())
        return httpx.Response(200, json={})

    async def go():
        client = SectorsClient(
            "k", transport=httpx.MockTransport(handler), min_interval=0.05
        )
        async with client:
            clone = client.with_new_log()
            await asyncio.gather(client.get("/a/"), clone.get("/b/"), client.get("/c/"))

    run(go())
    gaps = [b - a for a, b in itertools.pairwise(stamps)]
    assert all(gap >= 0.045 for gap in gaps)


def test_insufficient_credits_is_not_retried():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(
            429, json={"error": "INSUFFICIENT_CREDITS", "message": "no credits"}
        )

    async def go():
        client = SectorsClient(
            "k", transport=httpx.MockTransport(handler), retry_delays=(0, 0, 0)
        )
        async with client:
            await client.get("/daily/ANTM/")

    with pytest.raises(SectorsError, match="INSUFFICIENT_CREDITS"):
        run(go())
    assert len(calls) == 1
