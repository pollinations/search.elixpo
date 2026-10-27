"""Render service: egress proxy SSRF enforcement, auth, and the scrape client."""
import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lixsearch"))

import commons.url_safety as url_safety  # noqa: E402
from renderService import egress_proxy  # noqa: E402
from renderService import main as render_main  # noqa: E402
from renderService.egress_proxy import EgressProxy, address_allowed  # noqa: E402
from searching import scrape  # noqa: E402


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

async def _proxy_request(proxy: EgressProxy, raw: bytes) -> bytes:
    reader, writer = await asyncio.open_connection("127.0.0.1", proxy.port)
    writer.write(raw)
    await writer.drain()
    data = await asyncio.wait_for(reader.read(65536), 5)
    writer.close()
    return data


def _run_with_proxy(coro_fn, **kwargs):
    async def runner():
        proxy = EgressProxy("127.0.0.1", 0, **kwargs)
        await proxy.start()
        try:
            return await coro_fn(proxy)
        finally:
            await proxy.stop()
    return asyncio.run(runner())


def _status(data: bytes) -> int:
    return int(data.split(b" ", 2)[1])


@pytest.fixture
def fake_dns(monkeypatch):
    table = {}
    calls = []

    def resolve(hostname, port):
        calls.append(hostname)
        answer = table.get(hostname)
        if callable(answer):
            answer = answer()
        if not answer:
            raise url_safety.UnsafeURLError(f"Hostname could not be resolved: {hostname}")
        return set(answer)

    monkeypatch.setattr(url_safety, "resolve_host", resolve)
    return table, calls


# ---------------------------------------------------------------------------
# address policy
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("address", [
    "127.0.0.1", "10.1.2.3", "172.20.0.5", "172.31.250.10", "192.168.1.1", "169.254.169.254",
    "100.64.0.1", "0.0.0.0", "224.0.0.1", "168.63.129.16", "::1", "fd00::1", "fe80::1",
    "ff02::1", "::ffff:127.0.0.1", "64:ff9b::a00:1", "2002:a00:1::1", "not-an-ip",
])
def test_address_policy_refuses_internal(address):
    assert address_allowed(address) is False


def test_address_policy_allows_public_and_extra_deny():
    assert address_allowed("93.184.216.34") is True
    assert address_allowed("2606:2800:220:1:248:1893:25c8:1946") is True
    assert address_allowed("93.184.216.34", egress_proxy._parse_extra(["93.184.216.0/24"])) is False


def test_proxy_binds_loopback_only():
    with pytest.raises(ValueError):
        EgressProxy("0.0.0.0", 0)


# ---------------------------------------------------------------------------
# proxy refusals
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("target", [
    "127.0.0.1:443", "10.0.0.5:443", "169.254.169.254:80", "[::1]:443", "localhost:443",
    "metadata.google.internal:80", "[::ffff:169.254.169.254]:443",
])
def test_connect_to_internal_refused(target, fake_dns):
    async def go(proxy):
        return await _proxy_request(proxy, f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n".encode())

    data = _run_with_proxy(go)
    assert _status(data) == 403
    assert fake_dns[1] == []  # literal IPs / local names are refused without DNS


@pytest.mark.parametrize("uri", [
    "http://169.254.169.254/latest/meta-data/",
    "http://127.0.0.1/",
    "http://[::1]/",
    "http://192.168.0.1/admin",
])
def test_http_absolute_to_internal_refused(uri):
    async def go(proxy):
        return await _proxy_request(proxy, f"GET {uri} HTTP/1.1\r\nHost: x\r\n\r\n".encode())

    assert _status(_run_with_proxy(go)) == 403


def test_websocket_upgrade_to_internal_refused():
    raw = (b"GET http://127.0.0.1/ HTTP/1.1\r\nHost: 127.0.0.1\r\nUpgrade: websocket\r\n"
           b"Connection: Upgrade\r\nSec-WebSocket-Version: 13\r\n\r\n")

    async def go(proxy):
        return await _proxy_request(proxy, raw)

    assert _status(_run_with_proxy(go)) == 403


def test_hostname_with_any_private_answer_refused(fake_dns):
    table, _ = fake_dns
    table["mixed.example"] = {"93.184.216.34", "10.0.0.7"}
    table["internal.example"] = {"172.20.0.3"}

    async def go(proxy):
        a = await _proxy_request(proxy, b"CONNECT mixed.example:443 HTTP/1.1\r\n\r\n")
        b = await _proxy_request(proxy, b"GET http://internal.example/ HTTP/1.1\r\nHost: internal.example\r\n\r\n")
        return a, b, proxy.blocked

    a, b, blocked = _run_with_proxy(go)
    assert _status(a) == 403 and _status(b) == 403 and blocked == 2


def test_dns_rebinding_public_then_private_refused(fake_dns):
    """The page-level check sees a public answer; the proxy's own resolution at
    connect time sees the rebound private one and refuses."""
    table, calls = fake_dns
    answers = iter([{"93.184.216.34"}, {"127.0.0.1"}, {"127.0.0.1"}])
    table["rebind.example"] = lambda: next(answers)

    assert url_safety.check_public_url("https://rebind.example/") == "https://rebind.example/"

    async def go(proxy):
        return await _proxy_request(proxy, b"CONNECT rebind.example:443 HTTP/1.1\r\n\r\n")

    assert _status(_run_with_proxy(go)) == 403
    assert calls == ["rebind.example", "rebind.example"]


@pytest.mark.parametrize("target", ["93.184.216.34:22", "93.184.216.34:9530", "93.184.216.34:6333"])
def test_disallowed_ports_refused(target, fake_dns):
    async def go(proxy):
        return await _proxy_request(proxy, f"CONNECT {target} HTTP/1.1\r\n\r\n".encode())

    assert _status(_run_with_proxy(go)) == 403


def test_disallowed_port_on_absolute_uri_refused():
    async def go(proxy):
        return await _proxy_request(proxy, b"GET http://93.184.216.34:8080/ HTTP/1.1\r\nHost: x\r\n\r\n")

    assert _status(_run_with_proxy(go)) == 403


def test_non_http_scheme_and_garbage_refused():
    async def go(proxy):
        a = await _proxy_request(proxy, b"GET ftp://93.184.216.34/ HTTP/1.1\r\n\r\n")
        b = await _proxy_request(proxy, b"NONSENSE\r\n\r\n")
        return a, b

    a, b = _run_with_proxy(go)
    assert _status(a) == 400 and _status(b) == 400


# ---------------------------------------------------------------------------
# allowed relay (fake public host -> local test server)
# ---------------------------------------------------------------------------

def _allow_test_server(monkeypatch, fake_dns):
    table, _ = fake_dns
    table["public.example"] = {"127.0.0.1"}
    monkeypatch.setattr(egress_proxy, "address_allowed", lambda a, extra=(): a == "127.0.0.1")


def test_http_request_relayed_to_validated_ip(monkeypatch, fake_dns):
    _allow_test_server(monkeypatch, fake_dns)
    seen = {}

    async def origin(reader, writer):
        seen["head"] = (await reader.readuntil(b"\r\n\r\n")).decode()
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 5\r\nConnection: close\r\n\r\nhello")
        await writer.drain()
        writer.close()

    async def go():
        server = await asyncio.start_server(origin, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        proxy = EgressProxy("127.0.0.1", 0, allowed_ports={port})
        await proxy.start()
        try:
            return await _proxy_request(proxy, (
                f"GET http://public.example:{port}/hello?x=1 HTTP/1.1\r\nHost: public.example\r\n"
                "Proxy-Connection: keep-alive\r\nProxy-Authorization: Basic abc\r\n\r\n").encode())
        finally:
            await proxy.stop()
            server.close()

    data = asyncio.run(go())
    assert _status(data) == 200 and data.endswith(b"hello")
    head = seen["head"]
    assert head.startswith("GET /hello?x=1 HTTP/1.1\r\n")
    assert "Connection: close" in head
    assert "Proxy-" not in head


def test_connect_tunnel_relays_bytes(monkeypatch, fake_dns):
    _allow_test_server(monkeypatch, fake_dns)

    async def echo(reader, writer):
        data = await reader.read(100)
        writer.write(b"echo:" + data)
        await writer.drain()
        writer.close()

    async def go():
        server = await asyncio.start_server(echo, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        proxy = EgressProxy("127.0.0.1", 0, allowed_ports={port})
        await proxy.start()
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", proxy.port)
            writer.write(f"CONNECT public.example:{port} HTTP/1.1\r\n\r\n".encode())
            established = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 5)
            writer.write(b"ping")
            await writer.drain()
            reply = await asyncio.wait_for(reader.read(100), 5)
            writer.close()
            return established, reply
        finally:
            await proxy.stop()
            server.close()

    established, reply = asyncio.run(go())
    assert established.startswith(b"HTTP/1.1 200")
    assert reply == b"echo:ping"


def test_connection_cap(monkeypatch, fake_dns):
    async def go(proxy):
        proxy.active = proxy.max_connections  # simulate saturation
        return await _proxy_request(proxy, b"CONNECT 93.184.216.34:443 HTTP/1.1\r\n\r\n")

    assert _status(_run_with_proxy(go, max_connections=1)) == 503


# ---------------------------------------------------------------------------
# render service auth
# ---------------------------------------------------------------------------

class FakeRenderer:
    connected = True
    active = 0

    def __init__(self):
        self.calls = []

    async def render(self, url, timeout_ms, wait_for_ms, screenshot, full_page):
        self.calls.append((url, timeout_ms, wait_for_ms, screenshot, full_page))
        return {"url": url, "status_code": 200, "html": "<p>ok</p>", "screenshot": "QUJD" if screenshot else None,
                "error": None}


def _post(app, headers=None, body=None):
    async def go():
        client = app.test_client()
        return await client.post("/render", json=body or {"url": "https://93.184.216.34/"}, headers=headers or {})
    response = asyncio.run(go())
    return response.status_code, asyncio.run(response.get_json())


def test_render_requires_token():
    renderer = FakeRenderer()
    app = render_main.create_app(renderer=renderer, token="s3cret")
    assert _post(app)[0] == 401
    assert _post(app, {"X-Render-Token": "wrong"})[0] == 401
    assert renderer.calls == []
    status, body = _post(app, {"X-Render-Token": "s3cret"},
                         {"url": "https://93.184.216.34/", "timeout_ms": 999999, "wait_for_ms": -5,
                          "screenshot": True})
    assert status == 200 and body["html"] == "<p>ok</p>" and body["screenshot"] == "QUJD"
    url, timeout_ms, wait_for_ms, screenshot, _ = renderer.calls[0]
    assert timeout_ms <= render_main.config.SCRAPE_MAX_TIMEOUT_MS and wait_for_ms == 0 and screenshot


def test_render_refuses_when_token_unconfigured():
    renderer = FakeRenderer()
    app = render_main.create_app(renderer=renderer, token="")
    assert _post(app, {"X-Render-Token": ""})[0] == 503
    assert _post(app, {"X-Render-Token": "anything"})[0] == 503
    assert renderer.calls == []


def test_render_rejects_private_url_before_browser():
    renderer = FakeRenderer()
    app = render_main.create_app(renderer=renderer, token="t")
    status, body = _post(app, {"X-Render-Token": "t"}, {"url": "http://169.254.169.254/"})
    assert status == 200 and body["error"].startswith("UnsafeURLError") and renderer.calls == []


def test_token_compared_in_constant_time(monkeypatch):
    seen = []
    real = render_main.hmac.compare_digest
    monkeypatch.setattr(render_main.hmac, "compare_digest", lambda a, b: seen.append(1) or real(a, b))
    assert render_main.token_rejection("abc", "abc") is None
    assert render_main.token_rejection("abd", "abc")[0] == 401
    assert seen == [1, 1]


def test_chromium_args_force_proxy():
    args = render_main.chromium_args("http://127.0.0.1:4321")
    assert "--proxy-server=http://127.0.0.1:4321" in args
    assert "--proxy-bypass-list=<-loopback>" in args
    assert "--force-webrtc-ip-handling-policy=disable_non_proxied_udp" in args
    assert "--disable-quic" in args
    assert "--disable-web-security" not in args


# ---------------------------------------------------------------------------
# scrape client
# ---------------------------------------------------------------------------

class FakeHTTPResponse:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def _fake_session(monkeypatch, status, payload):
    calls = []

    class FakeSession:
        trust_env = True

        def post(self, url, json=None, headers=None, timeout=None):
            calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout,
                          "trust_env": self.trust_env})
            return FakeHTTPResponse(status, payload)

        def close(self):
            pass

    monkeypatch.setattr(scrape.requests, "Session", FakeSession)
    monkeypatch.setattr(scrape, "RENDER_SERVICE_TOKEN", "tok-123")
    monkeypatch.setattr(scrape, "RENDER_SERVICE_URL", "http://render-service:9520")
    return calls


def test_client_sends_token_and_parses(monkeypatch):
    calls = _fake_session(monkeypatch, 200, {"url": "https://example.com/final", "status_code": 201,
                                             "html": "<h1>x</h1>", "screenshot": "QUJD", "error": None})
    page = asyncio.run(scrape.browser_render("https://example.com/", 20000, 500, True, True))
    assert page.url == "https://example.com/final" and page.status_code == 201
    assert page.html == "<h1>x</h1>" and page.screenshot == "data:image/png;base64,QUJD"
    call = calls[0]
    assert call["url"] == "http://render-service:9520/render"
    assert call["headers"] == {"X-Render-Token": "tok-123"}
    assert call["json"] == {"url": "https://example.com/", "timeout_ms": 20000, "wait_for_ms": 500,
                            "screenshot": True, "full_page": True}
    assert call["trust_env"] is False and call["timeout"] > 20.5


def test_client_maps_failures(monkeypatch):
    _fake_session(monkeypatch, 200, {"url": "u", "status_code": None, "html": "", "screenshot": None,
                                     "error": "TimeoutError: x"})
    with pytest.raises(scrape.ScrapeError, match="Browser render failed"):
        asyncio.run(scrape.browser_render("https://example.com/", 1000, 0, False))

    _fake_session(monkeypatch, 401, {"error": "invalid render token"})
    with pytest.raises(scrape.ScrapeError) as exc:
        asyncio.run(scrape.browser_render("https://example.com/", 1000, 0, False))
    assert exc.value.status == 503


def test_client_fails_closed_without_token(monkeypatch):
    calls = _fake_session(monkeypatch, 200, {})
    monkeypatch.setattr(scrape, "RENDER_SERVICE_TOKEN", "")
    with pytest.raises(scrape.ScrapeError) as exc:
        asyncio.run(scrape.browser_render("https://example.com/", 1000, 0, False))
    assert exc.value.status == 503 and calls == []
