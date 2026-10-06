import asyncio
import copy
import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self

import certifi
import httpx

from bot.config import Settings

BASE_URL = "https://api.sectors.app/v2"
FIXTURES_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "sectors"
FIXTURE_NOT_FOUND = "FIXTURE_NOT_FOUND"
RETRY_DELAYS = (5, 10, 20, 40, 80, 160)
LIVE_MIN_INTERVAL = 0.35


def rate_limited(resp: httpx.Response) -> bool:
    if resp.status_code != 429:
        return False
    try:
        return resp.json().get("error") != "INSUFFICIENT_CREDITS"
    except ValueError:
        return True


class SectorsError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(f"{status} {code}: {message}")
        self.status = status
        self.code = code


class SectorsClient:
    def __init__(
        self,
        api_key: str,
        transport: httpx.AsyncBaseTransport | None = None,
        retry_delays: tuple[float, ...] = RETRY_DELAYS,
        min_interval: float = 0,
    ) -> None:
        self._http = httpx.AsyncClient(
            base_url=BASE_URL,
            headers={"Authorization": api_key},
            verify=certifi.where(),
            timeout=60,
            transport=transport,
        )
        self.log: list[dict[str, Any]] = []
        self._retry_delays = retry_delays
        self._min_interval = min_interval
        self._pace = {"lock": asyncio.Lock(), "last": 0.0}

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._http.aclose()

    def with_new_log(self) -> Self:
        clone = copy.copy(self)
        clone.log = []
        return clone

    async def _send(self, path: str, params: dict[str, Any]) -> httpx.Response:
        if self._min_interval:
            async with self._pace["lock"]:
                wait = self._pace["last"] + self._min_interval - time.monotonic()
                if wait > 0:
                    await asyncio.sleep(wait)
                self._pace["last"] = time.monotonic()
        return await self._http.get(path, params=params)

    async def get(self, path: str, *, missing_ok: bool = False, **params: Any) -> Any:
        resp = await self._send(path, params)
        for delay in self._retry_delays:
            if not rate_limited(resp):
                break
            await asyncio.sleep(delay)
            resp = await self._send(path, params)
        if resp.is_error:
            try:
                body = resp.json()
            except ValueError:
                body = None
            body = body if isinstance(body, dict) else {}
            code = body.get("error", "")
            if missing_ok and resp.status_code == 404 and code != FIXTURE_NOT_FOUND:
                return None
            raise SectorsError(
                resp.status_code, code, body.get("message", resp.reason_phrase)
            )
        credits = resp.headers.get("limit-consumption")
        self.log.append(
            {
                "endpoint": path,
                "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "credits": int(credits) if credits else None,
            }
        )
        return resp.json()

    async def get_all_pages(
        self, path: str, *, missing_ok: bool = False, **params: Any
    ) -> list[Any]:
        results: list[Any] = []
        offset = 0
        while offset is not None:
            body = await self.get(path, missing_ok=missing_ok, **params, offset=offset)
            if body is None:
                return results
            results.extend(body["results"])
            next_offset = body["pagination"]["next_offset"]
            if next_offset is not None and next_offset <= offset:
                raise SectorsError(
                    200,
                    "PAGINATION_STUCK",
                    f"next_offset {next_offset} tidak maju dari {offset}",
                )
            offset = next_offset
        return results


def fixture_candidates(request: httpx.Request) -> list[str]:
    path = request.url.path.removeprefix("/v2/").strip("/")
    params = request.url.params
    if path == "companies":
        query = "&".join(
            f"{k}={v}" for k, v in sorted(params.multi_items()) if k != "offset"
        )
        return [f"{path}/{hashlib.sha256(query.encode()).hexdigest()[:16]}"]
    if path.startswith("broker-summary/") and params.get("start"):
        return [f"{path}/{params['start']}"]
    symbol = params.get("symbol") or params.get("symbols")
    return [f"{path}/{symbol}", path] if symbol else [path]


def fixture_transport(root: Path, *overlays: Path) -> httpx.MockTransport:
    dirs = (*overlays, root)

    def handler(request: httpx.Request) -> httpx.Response:
        candidates = fixture_candidates(request)
        for rel in candidates:
            file = next((f for d in dirs if (f := d / f"{rel}.json").exists()), None)
            if file is not None:
                body = json.loads(file.read_text())
                if isinstance(body, dict) and "pagination" in body:
                    body["pagination"] |= {"has_next": False, "next_offset": None}
                return httpx.Response(200, json=body)
        return httpx.Response(
            404,
            json={
                "error": FIXTURE_NOT_FOUND,
                "message": f"fixture belum ada: {candidates[0]}",
            },
        )

    return httpx.MockTransport(handler)


class RecordingTransport(httpx.AsyncBaseTransport):
    def __init__(
        self, root: Path, live: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._root = root
        self._fixtures = fixture_transport(root)
        self._live = live or httpx.AsyncHTTPTransport(verify=certifi.where())
        self.saved: list[Path] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        file = self._root / f"{fixture_candidates(request)[0]}.json"
        if file.exists():
            return await self._fixtures.handle_async_request(request)
        resp = await self._live.handle_async_request(request)
        body = await resp.aread()
        if resp.status_code == 200:
            file.parent.mkdir(parents=True, exist_ok=True)
            data = json.loads(body)
            file.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
            self.saved.append(file)

        headers = {
            k: v
            for k, v in resp.headers.items()
            if k.lower()
            not in ("content-encoding", "content-length", "transfer-encoding")
        }
        return httpx.Response(resp.status_code, headers=headers, content=body)

    async def aclose(self) -> None:
        await self._live.aclose()


def make_client(settings: Settings) -> SectorsClient:
    key = settings.sectors_api_key.get_secret_value()
    if settings.sectors_offline:
        return SectorsClient(key, fixture_transport(FIXTURES_DIR))
    return SectorsClient(key, min_interval=LIVE_MIN_INTERVAL)
