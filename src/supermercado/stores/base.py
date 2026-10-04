"""StoreAdapter port, adapter errors, and the shared polite HTTP client."""

from __future__ import annotations

import json as _json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from supermercado.domain.models import Listing


class AdapterError(Exception):
    """Base class for every store adapter failure."""


class ApiKeyRejected(AdapterError):
    """The store rejected the public API key configured in stores.yaml."""


class BlockedError(AdapterError):
    """The store answered with an anti-bot page."""


class ResponseShapeError(AdapterError):
    """The response does not have the expected structure."""


class TransportError(AdapterError):
    """Network-level failure (DNS, TLS, reset, timeout)."""


class HttpError(AdapterError):
    def __init__(self, status: int, url: str) -> None:
        super().__init__(f"HTTP {status} from {url}")
        self.status = status
        self.url = url


@dataclass(frozen=True)
class RawResponse:
    status: int
    text: str

    def json(self) -> Any:
        try:
            return _json.loads(self.text)
        except ValueError as exc:
            raise ResponseShapeError(f"expected JSON, got: {self.text[:120]!r}") from exc


Transport = Callable[..., RawResponse]


def curl_transport(timeout: float = 30.0) -> Transport:
    """Real transport: curl_cffi with Chrome TLS impersonation."""
    from curl_cffi import requests as curl_requests
    from curl_cffi.requests.exceptions import RequestException

    session = curl_requests.Session(impersonate="chrome")

    def send(
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json: Any = None,
        cookies: dict[str, str] | None = None,
    ) -> RawResponse:
        try:
            response = session.request(
                method,
                url,
                headers=headers,
                params=params,
                json=json,
                cookies=cookies,
                timeout=timeout,
            )
        except RequestException as exc:
            raise TransportError(str(exc)) from exc
        return RawResponse(status=response.status_code, text=response.text)

    return send


class HttpClient:
    """One client per store: enforces the minimum interval and retries with backoff."""

    RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})

    def __init__(
        self,
        transport: Transport,
        *,
        min_interval: float = 1.5,
        max_retries: int = 3,
        backoff_base: float = 2.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._transport = transport
        self._min_interval = min_interval
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._clock = clock
        self._sleep = sleep
        self._last: float | None = None

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json: Any = None,
        cookies: dict[str, str] | None = None,
    ) -> RawResponse:
        attempt = 0
        while True:
            self._wait_turn()
            try:
                response = self._transport(
                    method, url, headers=headers, params=params, json=json, cookies=cookies
                )
            except TransportError:
                if attempt >= self._max_retries:
                    raise
            else:
                if response.status < 400:
                    return response
                if response.status not in self.RETRY_STATUSES or attempt >= self._max_retries:
                    raise HttpError(response.status, url)
            self._sleep(self._backoff_base * 2**attempt)
            attempt += 1

    def _wait_turn(self) -> None:
        now = self._clock()
        if self._last is not None:
            elapsed = now - self._last
            if elapsed < self._min_interval:
                self._sleep(self._min_interval - elapsed)
        self._last = self._clock()


class StoreAdapter(Protocol):
    store_id: str
    supports_search: bool

    def search(self, query: str) -> list[Listing]: ...

    def fetch(self, skus: list[str]) -> list[Listing]: ...
