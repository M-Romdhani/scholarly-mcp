"""Entrypoint: streamable HTTP transport, optional bearer auth, health check.

Run locally:   python -m app.main
On Railway:    python -m app.main   (PORT injected by the platform)
"""
import logging
import sys

import uvicorn
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from . import config
from .server import mcp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("scholarly-mcp")


class BearerAuthMiddleware(BaseHTTPMiddleware):
    """Shared-secret gate.

    A Railway service gets a public URL. Without this, anyone who finds it can
    spend the OpenAlex budget and use the contact email as their own. Health
    checks stay open so the platform can probe the service.
    """

    async def dispatch(self, request: Request, call_next):
        if request.url.path in ("/health", "/"):
            return await call_next(request)
        header = request.headers.get("authorization", "")
        expected = f"Bearer {config.MCP_AUTH_TOKEN}"
        # Length-then-compare is fine here; secrets.compare_digest for constant time.
        import secrets
        if not secrets.compare_digest(header, expected):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)


def _host_accepted(host_header: str | None) -> bool:
    """Would the MCP transport accept this Host header? Mirrors the SDK's
    TransportSecurityMiddleware._validate_host matching rules."""
    if not config.PUBLIC_HOSTNAME:
        return True  # protection disabled; everything is accepted
    if not host_header:
        return False
    for allowed in config.allowed_http_hosts():
        if host_header == allowed:
            return True
        if allowed.endswith(":*") and host_header.startswith(allowed[:-2] + ":"):
            return True
    return False


async def health(request: Request) -> JSONResponse:
    """Open so the platform can probe it — and deliberately reports whether /mcp
    would accept this same request.

    /health is a plain route; /mcp sits behind the transport's Host validation.
    Without this check a misconfigured PUBLIC_HOSTNAME gives a green deploy in
    front of a server that answers 421 to every MCP call. Reporting a healthy
    status while the actual service is unreachable is exactly the silent
    degradation identity.md rule 6 forbids.
    """
    host_header = request.headers.get("host")
    ok = _host_accepted(host_header)
    warnings = []
    if not config.PUBLIC_HOSTNAME:
        warnings.append(
            "PUBLIC_HOSTNAME (or RAILWAY_PUBLIC_DOMAIN) is not set, so Host-header "
            "validation is disabled. Set it to this service's public hostname.")
    elif not ok:
        warnings.append(
            f"THIS REQUEST'S Host header ({host_header!r}) would be REJECTED by "
            f"/mcp with HTTP 421. PUBLIC_HOSTNAME is {config.PUBLIC_HOSTNAME!r}. "
            f"MCP calls will fail even though this health check passes.")
    if not config.MCP_AUTH_TOKEN:
        warnings.append("MCP_AUTH_TOKEN is not set — /mcp is open to anyone.")
    return JSONResponse({
        "status": "ok",
        "request_host_header": host_header,
        "mcp_would_accept_this_host": ok,
        "warnings": warnings,
        **config.startup_report(),
    })


def build_app():
    try:
        config.require_email()
    except config.ConfigError as e:
        log.error("%s", e)
        sys.exit(1)

    if not config.OPENALEX_API_KEY:
        log.warning("OPENALEX_API_KEY not set — daily budget is $0.10 instead of "
                    "$1.00. Free key: openalex.org/settings/api")
    if not config.MCP_AUTH_TOKEN:
        log.warning("MCP_AUTH_TOKEN not set — this endpoint is PUBLIC. Anyone "
                    "with the URL can spend your API budget. Set it.")

    if config.PUBLIC_HOSTNAME:
        transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=config.allowed_http_hosts(),
            allowed_origins=[f"https://{config.PUBLIC_HOSTNAME}",
                             f"http://{config.PUBLIC_HOSTNAME}"],
        )
        log.info("Host-header validation ON; accepting %s",
                 config.allowed_http_hosts())
    else:
        # Passed explicitly. Omitting it lets the SDK default host="127.0.0.1",
        # which auto-enables protection for localhost ONLY — so every request
        # arriving on a real domain is answered 421 while /health still returns
        # 200. That is a green deploy in front of a dead server.
        transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=False)
        log.warning("PUBLIC_HOSTNAME not set — Host-header validation DISABLED. "
                    "Set PUBLIC_HOSTNAME to this service's public hostname "
                    "(Railway sets RAILWAY_PUBLIC_DOMAIN automatically).")

    app = mcp.streamable_http_app(streamable_http_path="/mcp",
                                  stateless_http=True,
                                  transport_security=transport_security)
    app.router.routes.append(Route("/health", health, methods=["GET"]))
    if config.MCP_AUTH_TOKEN:
        app.add_middleware(BearerAuthMiddleware)

    log.info("scholarly-mcp ready on /mcp — %s", config.startup_report())
    return app


app = build_app()

if __name__ == "__main__":
    uvicorn.run(app, host=config.HOST, port=config.PORT, log_level="info")
