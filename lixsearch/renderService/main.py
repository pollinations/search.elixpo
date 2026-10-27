"""Isolated page-render service (APP_MODE=render).

Runs one Chromium whose every request is forced through the loopback egress
proxy (see egress_proxy.py). Each render gets a fresh browser context that is
closed afterwards, so pages share no cookies, storage or cache.

POST /render  {url, timeout_ms, wait_for_ms, screenshot, full_page}
              -> {url, status_code, html, screenshot, error}
              requires X-Render-Token == RENDER_SERVICE_TOKEN
GET  /health
"""
from __future__ import annotations

import asyncio
import base64
import hmac
import os
import random
import sys
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger  # noqa: E402
from quart import Quart, jsonify, request  # noqa: E402

from commons.url_safety import UnsafeURLError, check_public_url  # noqa: E402
from pipeline import config  # noqa: E402
from renderService.egress_proxy import EgressProxy  # noqa: E402

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]
_STEALTH = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
window.chrome = {runtime: {}};
"""


def _error_result(url: str, message: str) -> dict:
    return {"url": url, "status_code": None, "html": "", "screenshot": None, "error": message}


def chromium_args(proxy_url: str) -> list[str]:
    return [
        f"--proxy-server={proxy_url}",
        "--proxy-bypass-list=<-loopback>",  # loopback goes through the proxy too
        "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
        "--disable-quic",
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-default-apps",
        "--disable-sync",
        "--no-first-run",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-blink-features=AutomationControlled",
    ]


class BrowserRenderer:
    """One shared Chromium, one fresh context per render, relaunched on crash."""

    def __init__(self, proxy_url: str, max_concurrency: int):
        self.proxy_url = proxy_url
        self.semaphore = asyncio.Semaphore(max(1, max_concurrency))
        self._lock = asyncio.Lock()
        self._playwright = None
        self._browser = None
        self.active = 0
        self.launches = 0

    @property
    def connected(self) -> bool:
        return self._browser is not None and self._browser.is_connected()

    async def _browser_ready(self):
        async with self._lock:
            if self.connected:
                return self._browser
            if self._browser is not None:
                logger.warning("[Render] Browser disconnected; relaunching")
                try:
                    await self._browser.close()
                except Exception:
                    pass
                self._browser = None
            if self._playwright is None:
                from playwright.async_api import async_playwright
                self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=config.isHeadless, args=chromium_args(self.proxy_url))
            self.launches += 1
            logger.info(f"[Render] Chromium launched (#{self.launches}) via proxy {self.proxy_url}")
            return self._browser

    async def start(self):
        await self._browser_ready()

    async def close(self):
        async with self._lock:
            for closer in (self._browser, self._playwright):
                if closer is None:
                    continue
                try:
                    await (closer.close() if closer is self._browser else closer.stop())
                except Exception:
                    pass
            self._browser = self._playwright = None

    async def render(self, url: str, timeout_ms: int, wait_for_ms: int,
                     screenshot: bool, full_page: bool) -> dict:
        async with self.semaphore:
            self.active += 1
            try:
                return await self._render_once(url, timeout_ms, wait_for_ms, screenshot, full_page)
            finally:
                self.active -= 1

    async def _render_once(self, url, timeout_ms, wait_for_ms, screenshot, full_page) -> dict:
        verdicts: dict[str, bool] = {}

        async def guard(route):
            # Early-reject layer; the egress proxy is the actual enforcement point.
            request_url = route.request.url
            origin = "/".join(request_url.split("/", 3)[:3])
            allowed = verdicts.get(origin)
            if allowed is None:
                try:
                    await asyncio.to_thread(check_public_url, request_url)
                    allowed = True
                except Exception:
                    allowed = False
                verdicts[origin] = allowed
            if allowed:
                await route.continue_()
            else:
                logger.warning(f"[Render] Blocked non-public browser request: {request_url[:200]}")
                await route.abort()

        context = None
        try:
            try:
                browser = await self._browser_ready()
                context = await browser.new_context(
                    user_agent=random.choice(_USER_AGENTS),
                    viewport={"width": 1366, "height": 900},
                    service_workers="block",
                    accept_downloads=False,
                )
            except Exception as exc:
                # A crashed browser surfaces here; force one relaunch and retry.
                logger.warning(f"[Render] Context creation failed ({type(exc).__name__}); restarting browser")
                async with self._lock:
                    if self._browser is not None:
                        try:
                            await self._browser.close()
                        except Exception:
                            pass
                        self._browser = None
                browser = await self._browser_ready()
                context = await browser.new_context(
                    user_agent=random.choice(_USER_AGENTS),
                    viewport={"width": 1366, "height": 900},
                    service_workers="block",
                    accept_downloads=False,
                )
            await context.add_init_script(_STEALTH)
            await context.route("**/*", guard)
            page = await context.new_page()
            response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            if wait_for_ms:
                await page.wait_for_timeout(wait_for_ms)
            final_url = page.url
            await asyncio.to_thread(check_public_url, final_url)
            html = await page.content()
            shot = None
            if screenshot:
                png = await page.screenshot(full_page=bool(full_page), type="png", timeout=timeout_ms)
                shot = base64.b64encode(png).decode("ascii")
            return {
                "url": final_url,
                "status_code": response.status if response is not None else 200,
                "html": html,
                "screenshot": shot,
                "error": None,
            }
        except Exception as exc:
            logger.warning(f"[Render] Render failed for {url[:200]}: {type(exc).__name__}: {str(exc)[:200]}")
            return _error_result(url, f"{type(exc).__name__}: {str(exc)[:300]}")
        finally:
            if context is not None:
                try:
                    await context.close()
                except Exception:
                    pass


def token_rejection(provided: Optional[str], expected: str):
    """Return (status, message) when the request must be refused, else None."""
    if not expected:
        return 503, "render service token not configured"
    if not provided or not hmac.compare_digest(provided.encode(), expected.encode()):
        return 401, "invalid render token"
    return None


def _clamp(value, low: int, high: int, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(low, min(high, number))


def create_app(renderer=None, token: Optional[str] = None, proxy: Optional[EgressProxy] = None) -> Quart:
    app = Quart(__name__)
    app.config["MAX_CONTENT_LENGTH"] = config.RENDER_MAX_REQUEST_BYTES
    expected = config.RENDER_SERVICE_TOKEN if token is None else token
    state = {"renderer": renderer, "proxy": proxy}

    @app.before_serving
    async def _startup():
        if not expected:
            logger.error("[Render] RENDER_SERVICE_TOKEN is not set: refusing all /render requests "
                         "(set it in .env.local for render-service and lixsearch-app)")
        if state["renderer"] is None:
            state["proxy"] = state["proxy"] or EgressProxy.from_config()
            await state["proxy"].start()
            state["renderer"] = BrowserRenderer(state["proxy"].url, config.RENDER_MAX_CONCURRENCY)
            await state["renderer"].start()

    @app.after_serving
    async def _shutdown():
        if isinstance(state["renderer"], BrowserRenderer):
            await state["renderer"].close()
        if state["proxy"] is not None:
            await state["proxy"].stop()

    @app.get("/health")
    async def health():
        r, p = state["renderer"], state["proxy"]
        connected = bool(getattr(r, "connected", r is not None))
        return jsonify({
            "status": "healthy" if connected and expected else "degraded",
            "browser_connected": connected,
            "token_configured": bool(expected),
            "active_renders": getattr(r, "active", 0),
            "proxy_active_connections": getattr(p, "active", 0),
            "proxy_blocked": getattr(p, "blocked", 0),
        }), 200 if connected and expected else 503  # unhealthy until the token is set

    @app.post("/render")
    async def render():
        refusal = token_rejection(request.headers.get("X-Render-Token"), expected)
        if refusal:
            status, message = refusal
            if status == 503:
                logger.error("[Render] Refused /render: RENDER_SERVICE_TOKEN is not configured")
            else:
                logger.warning(f"[Render] Refused /render from {request.remote_addr}: {message}")
            return jsonify({"error": message}), status
        body = await request.get_json(silent=True)
        if not isinstance(body, dict) or not isinstance(body.get("url"), str):
            return jsonify({"error": "body must be JSON with a string url"}), 400
        url = body["url"]
        timeout_ms = _clamp(body.get("timeout_ms"), 1000, config.SCRAPE_MAX_TIMEOUT_MS,
                            config.SCRAPE_DEFAULT_TIMEOUT_MS)
        wait_for_ms = _clamp(body.get("wait_for_ms"), 0, config.SCRAPE_MAX_WAIT_FOR_MS, 0)
        try:
            url = await asyncio.to_thread(check_public_url, url, max_chars=config.SCRAPE_MAX_URL_CHARS)
        except UnsafeURLError as exc:
            return jsonify(_error_result(body["url"], f"UnsafeURLError: {exc}"))
        if state["renderer"] is None:
            return jsonify(_error_result(url, "renderer not ready")), 503
        budget = (timeout_ms * 2 + wait_for_ms) / 1000 + 10
        try:
            result = await asyncio.wait_for(
                state["renderer"].render(url, timeout_ms, wait_for_ms,
                                         bool(body.get("screenshot")), bool(body.get("full_page"))),
                budget)
        except asyncio.TimeoutError:
            result = _error_result(url, f"TimeoutError: render exceeded {budget:.0f}s")
        return jsonify(result)

    return app


def main():
    import hypercorn.asyncio
    from hypercorn.config import Config

    cfg = Config()
    cfg.bind = [f"{config.RENDER_HOST}:{config.RENDER_PORT}"]
    cfg.workers = 1  # one Chromium per container; concurrency is RENDER_MAX_CONCURRENCY
    logger.info(f"[Render] Starting render service on {config.RENDER_HOST}:{config.RENDER_PORT}")
    asyncio.run(hypercorn.asyncio.serve(create_app(), cfg))


if __name__ == "__main__":
    main()
