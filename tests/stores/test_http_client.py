import pytest

from fakes import FakeClock, FakeTransport, make_client, ok
from supermercado.stores.base import HttpError, RawResponse, ResponseShapeError, TransportError


def test_returns_successful_response_and_forwards_arguments() -> None:
    transport = FakeTransport([ok('{"a": 1}')])
    response = make_client(transport).request(
        "POST", "https://x.test/p", headers={"h": "1"}, json={"q": 1}, cookies={"c": "2"}
    )
    assert response.json() == {"a": 1}
    call = transport.calls[0]
    assert (call["method"], call["url"], call["headers"], call["json"], call["cookies"]) == (
        "POST",
        "https://x.test/p",
        {"h": "1"},
        {"q": 1},
        {"c": "2"},
    )


def test_waits_min_interval_between_requests() -> None:
    clock = FakeClock()
    client = make_client(FakeTransport([ok("{}"), ok("{}")]), clock)
    client.request("GET", "https://x.test/1")
    client.request("GET", "https://x.test/2")
    assert clock.sleeps == [1.5]


def test_no_wait_when_interval_already_elapsed() -> None:
    clock = FakeClock()
    client = make_client(FakeTransport([ok("{}"), ok("{}")]), clock)
    client.request("GET", "https://x.test/1")
    clock.advance(2.0)
    client.request("GET", "https://x.test/2")
    assert clock.sleeps == []


def test_retries_retryable_status_with_exponential_backoff() -> None:
    clock = FakeClock()
    transport = FakeTransport([RawResponse(503, ""), RawResponse(429, ""), ok("{}")])
    assert make_client(transport, clock).request("GET", "https://x.test").status == 200
    assert clock.sleeps == [2.0, 4.0]


def test_gives_up_after_three_retries() -> None:
    clock = FakeClock()
    transport = FakeTransport([RawResponse(503, "")] * 4)
    with pytest.raises(HttpError) as excinfo:
        make_client(transport, clock).request("GET", "https://x.test")
    assert excinfo.value.status == 503
    assert len(transport.calls) == 4
    assert clock.sleeps == [2.0, 4.0, 8.0]


def test_client_errors_are_not_retried() -> None:
    transport = FakeTransport([RawResponse(404, "")])
    with pytest.raises(HttpError) as excinfo:
        make_client(transport).request("GET", "https://x.test/missing")
    assert excinfo.value.status == 404
    assert len(transport.calls) == 1


def test_transport_errors_are_retried_then_propagated() -> None:
    transport = FakeTransport([TransportError("reset"), ok("{}")])
    assert make_client(transport).request("GET", "https://x.test").status == 200
    failing = FakeTransport([TransportError("reset")] * 4)
    with pytest.raises(TransportError):
        make_client(failing).request("GET", "https://x.test")
    assert len(failing.calls) == 4


def test_non_json_body_raises_shape_error() -> None:
    with pytest.raises(ResponseShapeError):
        RawResponse(200, "<html>blocked</html>").json()


def test_network_is_blocked_in_tests() -> None:
    from curl_cffi import requests

    with pytest.raises(RuntimeError, match="network"):
        requests.Session(impersonate="chrome").request("GET", "https://example.com")
