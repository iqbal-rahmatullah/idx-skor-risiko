import copy
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self

import certifi
import httpx

from bot.config import Settings

BASE_URL = "https://api.sectors.app/v2"
FIXTURES_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "sectors"
FIXTURE_NOT_FOUND = "FIXTURE_NOT_FOUND"


class SectorsError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(f"{status} {code}: {message}")
        self.status = status
        self.code = code


class SectorsClient:
    def __init__(
        self, api_key: str, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._http = httpx.AsyncClient(
            base_url=BASE_URL,
            headers={"Authorization": api_key},
            verify=certifi.where(),
            timeout=60,
            transport=transport,
        )
        self.log: list[dict[str, Any]] = []

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._http.aclose()

    def with_new_log(self) -> Self:
        clone = copy.copy(self)
        clone.log = []
        return clone

    async def get(self, path: str, *, missing_ok: bool = False, **params: Any) -> Any:
        resp = await self._http.get(path, params=params)
        if resp.is_error:
            try:
                body = resp.json()
            except ValueError:
                body = None
            body = body if isinstance(body, dict) else {}
            code = body.get("error", "")
            # 404 berarti emiten tidak punya data itu; fixture yang hilang tetap gagal keras.
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
    symbol = request.url.params.get("symbol") or request.url.params.get("symbols")
    return [f"{path}/{symbol}", path] if symbol else [path]


def fixture_transport(root: Path) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        candidates = fixture_candidates(request)
        for rel in candidates:
            file = root / f"{rel}.json"
            if file.exists():
                body = json.loads(file.read_text())
                if isinstance(body, dict) and "pagination" in body:
                    # Fixture hanya satu halaman; tanpa ini get_all_pages berputar selamanya.
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
        resp = await self._fixtures.handle_async_request(request)
        if resp.status_code != 404:
            return resp
        resp = await self._live.handle_async_request(request)
        body = await resp.aread()
        if resp.status_code == 200:
            file = self._root / f"{fixture_candidates(request)[0]}.json"
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
    transport = fixture_transport(FIXTURES_DIR) if settings.sectors_offline else None
    return SectorsClient(settings.sectors_api_key.get_secret_value(), transport)
