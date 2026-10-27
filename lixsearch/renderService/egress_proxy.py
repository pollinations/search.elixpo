"""Filtering HTTP forward proxy for the render-service browser.

Chromium is launched with ``--proxy-server`` pointing here, so every
navigation, subresource, fetch/XHR, WebSocket and (TCP-only) WebRTC request
leaves through this proxy. For each request the proxy:

1. checks the port against ``RENDER_PROXY_ALLOWED_PORTS``;
2. resolves the hostname itself and requires EVERY returned address to be
   public (url_safety's check plus an explicit deny list);
3. connects to one of those validated addresses — never re-resolving — so a
   DNS-rebinding answer between the check and the connect cannot redirect it.

Supported: ``CONNECT host:port`` (HTTPS / WSS, and Chromium's ws:// tunnels)
and absolute-URI ``GET http://host/...`` (plain HTTP / ws:// upgrades).
"""
from __future__ import annotations

import asyncio
import ipaddress
from typing import Iterable, Optional
from urllib.parse import urlsplit

from loguru import logger

from commons import url_safety

# Explicit deny list on top of ipaddress.is_global (defence in depth, and
# covers prefixes is_global treats as global but that reach host-internal or
# private space: NAT64, 6to4 and the Azure platform endpoint).
_DENY_NETWORKS = tuple(ipaddress.ip_network(n) for n in (
    "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16",
    "172.16.0.0/12", "192.0.0.0/24", "192.0.2.0/24", "192.168.0.0/16", "198.18.0.0/15",
    "198.51.100.0/24", "203.0.113.0/24", "224.0.0.0/4", "240.0.0.0/4",
    "168.63.129.16/32",  # Azure WireServer / host DNS: publicly numbered, host-internal
    "::/128", "::1/128", "64:ff9b::/96", "64:ff9b:1::/48", "100::/64", "2001:db8::/32",
    "2002::/16", "fc00::/7", "fe80::/10", "fec0::/10", "ff00::/8",
))

_MAX_HEADER_BYTES = 32 * 1024
_HOP_HEADERS = {"proxy-connection", "proxy-authorization", "keep-alive", "connection"}


class ProxyRefused(Exception):
    def __init__(self, status: int, reason: str):
        super().__init__(reason)
        self.status = status
        self.reason = reason


def _parse_extra(cidrs: Iterable[str]):
    nets = []
    for cidr in cidrs:
        try:
            nets.append(ipaddress.ip_network(cidr, strict=False))
        except ValueError:
            logger.warning(f"[Render] Ignoring invalid RENDER_PROXY_DENY_CIDRS entry: {cidr!r}")
    return tuple(nets)


def address_allowed(address: str, extra_deny: tuple = ()) -> bool:
    """True only for a globally routable, non-denied unicast address."""
    try:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    try:
        if not url_safety._ip_is_public(str(ip)):
            return False
    except ValueError:
        return False
    return not any(ip.version == net.version and ip in net for net in _DENY_NETWORKS + tuple(extra_deny))


def _split_hostport(authority: str, default_port: Optional[int]) -> tuple[str, int]:
    authority = authority.strip()
    if authority.startswith("["):
        end = authority.find("]")
        if end < 0:
            raise ProxyRefused(400, "malformed IPv6 authority")
        host, rest = authority[1:end], authority[end + 1:]
        port_text = rest[1:] if rest.startswith(":") else ""
    elif authority.count(":") == 1:
        host, port_text = authority.split(":", 1)
    elif ":" in authority:
        raise ProxyRefused(400, "unbracketed IPv6 authority")
    else:
        host, port_text = authority, ""
    if port_text:
        if not port_text.isdigit():
            raise ProxyRefused(400, "invalid port")
        port = int(port_text)
    elif default_port is not None:
        port = default_port
    else:
        raise ProxyRefused(400, "missing port")
    host = host.rstrip(".").lower()
    if not host or not 0 < port < 65536:
        raise ProxyRefused(400, "invalid target")
    return host, port


class EgressProxy:
    def __init__(self, host: str = "127.0.0.1", port: int = 0, *,
                 allowed_ports: Iterable[int] = (80, 443),
                 deny_cidrs: Iterable[str] = (),
                 max_connections: int = 256,
                 header_timeout: float = 10.0,
                 connect_timeout: float = 10.0,
                 idle_timeout: float = 60.0,
                 max_tunnel_seconds: float = 300.0):
        if host not in ("127.0.0.1", "::1"):
            raise ValueError("The egress proxy must bind to loopback only")
        self.host = host
        self.port = port
        self.allowed_ports = frozenset(int(p) for p in allowed_ports)
        self.extra_deny = _parse_extra(deny_cidrs)
        self.max_connections = max(1, int(max_connections))
        self.header_timeout = header_timeout
        self.connect_timeout = connect_timeout
        self.idle_timeout = idle_timeout
        self.max_tunnel_seconds = max_tunnel_seconds
        self.active = 0
        self.blocked = 0
        self._server: Optional[asyncio.base_events.Server] = None

    @classmethod
    def from_config(cls) -> "EgressProxy":
        from pipeline import config
        return cls("127.0.0.1", config.RENDER_PROXY_PORT,
                   allowed_ports=config.RENDER_PROXY_ALLOWED_PORTS,
                   deny_cidrs=config.RENDER_PROXY_DENY_CIDRS,
                   max_connections=config.RENDER_PROXY_MAX_CONNECTIONS,
                   header_timeout=config.RENDER_PROXY_HEADER_TIMEOUT_SECONDS,
                   connect_timeout=config.RENDER_PROXY_CONNECT_TIMEOUT_SECONDS,
                   idle_timeout=config.RENDER_PROXY_IDLE_TIMEOUT_SECONDS,
                   max_tunnel_seconds=config.RENDER_PROXY_MAX_TUNNEL_SECONDS)

    # -- lifecycle -----------------------------------------------------------
    async def start(self) -> int:
        self._server = await asyncio.start_server(self._handle, self.host, self.port,
                                                  limit=_MAX_HEADER_BYTES)
        self.port = self._server.sockets[0].getsockname()[1]
        logger.info(f"[Render] Egress proxy listening on {self.host}:{self.port} "
                    f"(ports={sorted(self.allowed_ports)}, max_conn={self.max_connections})")
        return self.port

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    # -- target validation ---------------------------------------------------
    async def resolve_target(self, host: str, port: int) -> list[str]:
        """Return validated public addresses for host:port or raise ProxyRefused."""
        if port not in self.allowed_ports:
            raise ProxyRefused(403, f"port {port} not allowed")
        if host in url_safety._BLOCKED_HOSTNAMES or host.endswith(url_safety._BLOCKED_SUFFIXES):
            raise ProxyRefused(403, "local hostname")
        try:
            ipaddress.ip_address(host.split("%", 1)[0])
            addresses = [host]
        except ValueError:
            try:
                resolved = await asyncio.wait_for(
                    asyncio.to_thread(url_safety.resolve_host, host, port), self.connect_timeout)
            except (url_safety.UnsafeURLError, asyncio.TimeoutError) as exc:
                raise ProxyRefused(502, f"resolution failed: {exc}") from exc
            # IPv4 first: the container network has no IPv6 route.
            addresses = sorted(resolved, key=lambda a: (":" in a, a))
        if not addresses:
            raise ProxyRefused(502, "no addresses")
        bad = [a for a in addresses if not address_allowed(a, self.extra_deny)]
        if bad:
            raise ProxyRefused(403, f"non-public address {bad[0]}")
        return addresses

    async def _open_pinned(self, addresses: list[str], port: int):
        last: Optional[BaseException] = None
        for address in addresses:
            try:
                return await asyncio.wait_for(asyncio.open_connection(address, port),
                                              self.connect_timeout)
            except (OSError, asyncio.TimeoutError) as exc:
                last = exc
        raise ProxyRefused(502, f"connect failed: {type(last).__name__}")

    # -- request handling ----------------------------------------------------
    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        if self.active >= self.max_connections:
            logger.warning("[Render] Proxy at capacity; refusing connection")
            await self._reply(writer, 503, "proxy at capacity")
            await self._close(writer)
            return
        self.active += 1
        target = "?"
        try:
            try:
                head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), self.header_timeout)
            except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, asyncio.TimeoutError,
                    ConnectionError):
                await self._reply(writer, 400, "bad request head")
                return
            lines = head.decode("latin-1").split("\r\n")
            parts = lines[0].split(" ")
            if len(parts) != 3 or not parts[2].startswith("HTTP/"):
                raise ProxyRefused(400, "malformed request line")
            method, uri, version = parts
            if method.upper() == "CONNECT":
                host, port = _split_hostport(uri, None)
                target = f"CONNECT {host}:{port}"
                addresses = await self.resolve_target(host, port)
                up_reader, up_writer = await self._open_pinned(addresses, port)
                writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                await writer.drain()
            else:
                split = urlsplit(uri)
                if split.scheme.lower() != "http" or not split.netloc or "@" in split.netloc:
                    raise ProxyRefused(400, "only absolute http:// URIs are proxied")
                host, port = _split_hostport(split.netloc, 80)
                target = f"{method} http://{host}:{port}"
                addresses = await self.resolve_target(host, port)
                up_reader, up_writer = await self._open_pinned(addresses, port)
                path = split.path or "/"
                if split.query:
                    path += "?" + split.query
                headers = [h for h in lines[1:] if h]
                upgrade = any(h.lower().startswith("upgrade:") for h in headers)
                out = [f"{method} {path} {version}"]
                out += [h for h in headers if h.split(":", 1)[0].strip().lower() not in _HOP_HEADERS]
                # One request per upstream connection: the browser may reuse a
                # proxy connection for a different host, so never keep-alive.
                out.append("Connection: Upgrade" if upgrade else "Connection: close")
                up_writer.write(("\r\n".join(out) + "\r\n\r\n").encode("latin-1"))
                await up_writer.drain()
            logger.debug(f"[Render] Proxy allowed {target} -> {addresses[0]}")
            await self._relay(reader, writer, up_reader, up_writer)
        except ProxyRefused as exc:
            if exc.status == 403:
                self.blocked += 1
                logger.warning(f"[Render] Proxy blocked {target}: {exc.reason}")
            else:
                logger.info(f"[Render] Proxy refused {target}: {exc.reason}")
            await self._reply(writer, exc.status, exc.reason)
        except Exception as exc:  # never let one connection kill the server
            logger.warning(f"[Render] Proxy error on {target}: {type(exc).__name__}: {exc}")
            await self._reply(writer, 502, "proxy error")
        finally:
            self.active -= 1
            await self._close(writer)

    async def _relay(self, reader, writer, up_reader, up_writer):
        async def pump(src, dst):
            try:
                while True:
                    chunk = await asyncio.wait_for(src.read(65536), self.idle_timeout)
                    if not chunk:
                        break
                    dst.write(chunk)
                    await dst.drain()
            except (ConnectionError, asyncio.TimeoutError, OSError):
                pass
            finally:
                try:
                    if dst.can_write_eof():
                        dst.write_eof()
                except (OSError, RuntimeError):
                    pass

        tasks = [asyncio.create_task(pump(reader, up_writer)),
                 asyncio.create_task(pump(up_reader, writer))]
        try:
            # Finish when the upstream side is done (or the lifetime cap hits).
            await asyncio.wait_for(tasks[1], self.max_tunnel_seconds)
        except asyncio.TimeoutError:
            pass
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await self._close(up_writer)

    @staticmethod
    async def _reply(writer, status: int, reason: str):
        text = {400: "Bad Request", 403: "Forbidden", 502: "Bad Gateway",
                503: "Service Unavailable"}.get(status, "Error")
        body = f"{reason}\n".encode()
        try:
            writer.write(f"HTTP/1.1 {status} {text}\r\nContent-Type: text/plain\r\n"
                         f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode() + body)
            await writer.drain()
        except Exception:
            pass

    @staticmethod
    async def _close(writer):
        try:
            if not writer.is_closing():
                writer.close()
            await asyncio.wait_for(writer.wait_closed(), 2)
        except Exception:
            pass
