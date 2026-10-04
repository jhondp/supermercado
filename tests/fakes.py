"""Fakes for HTTP transport, time, and recorded fixtures."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from supermercado.domain.models import Listing
from supermercado.stores.base import HttpClient, RawResponse

FIXTURES = Path(__file__).parent / "fixtures"


class FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.now = start
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeTransport:
    """Returns queued responses (or raises queued exceptions) and records every call."""

    def __init__(self, responses: list[RawResponse | Exception]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json: Any = None,
        cookies: dict[str, str] | None = None,
    ) -> RawResponse:
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": headers or {},
                "params": params or {},
                "json": json,
                "cookies": cookies or {},
            }
        )
        if not self.responses:
            raise AssertionError(f"unexpected request: {method} {url}")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def make_client(transport: FakeTransport, clock: FakeClock | None = None) -> HttpClient:
    clock = clock or FakeClock()
    return HttpClient(transport, clock=clock, sleep=clock.sleep)


def ok(text: str) -> RawResponse:
    return RawResponse(status=200, text=text)


def fixture_text(store: str, name: str) -> str:
    return (FIXTURES / store / name).read_text(encoding="utf-8")


def fixture_response(store: str, name: str, status: int = 200) -> RawResponse:
    return RawResponse(status=status, text=fixture_text(store, name))


def assert_recorded_listings(listings: list[Listing]) -> None:
    """Sanity checks for parsers run over real recorded responses."""
    assert listings, "recorded fixture produced no listings"
    assert all(listing.sku and listing.name for listing in listings)
    priced = [listing for listing in listings if listing.price and listing.price > 0]
    assert len(priced) >= 0.9 * len(listings), "most recorded listings should carry a price"


class FakeAdapter:
    """In-memory StoreAdapter for pipeline tests."""

    def __init__(
        self,
        store_id: str,
        listings: list[Listing] | tuple[Listing, ...] = (),
        *,
        error: Exception | None = None,
        supports_search: bool = True,
        search_results: dict[str, list[Listing]] | None = None,
    ) -> None:
        self.store_id = store_id
        self.supports_search = supports_search
        self._listings = list(listings)
        self._error = error
        self._search_results = dict(search_results or {})
        self.fetched: list[list[str]] = []
        self.searched: list[str] = []

    def fetch(self, skus: list[str]) -> list[Listing]:
        self.fetched.append(list(skus))
        if self._error is not None:
            raise self._error
        return [listing for listing in self._listings if listing.sku in skus]

    def search(self, query: str) -> list[Listing]:
        self.searched.append(query)
        if self._error is not None:
            raise self._error
        return list(self._search_results.get(query, []))
