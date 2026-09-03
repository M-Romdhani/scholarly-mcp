"""HTTP layer: allowlist enforcement, SSRF guard, backoff, budget capture.

Every outbound request in this server goes through `fetch()`. There is no other
path to the network, and `fetch()` refuses any host not in ALLOWED_HOSTS —
including after a redirect.
"""
import ipaddress
import json
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from . import config

# Most recent OpenAlex budget headers seen, for budget_status().
_last_openalex_budget: dict[str, str] = {}
_last_openalex_seen_at: float | None = None

# Per-host minimum spacing between requests, seconds.
#   arXiv asks for roughly one request every 3 seconds.
#   Semantic Scholar issues keys with a documented limit of 1 request per second
#   CUMULATIVE ACROSS ALL ENDPOINTS, so search and citation calls share one
#   budget. Exceeding it gets requests rejected, and the retry path then costs
#   more time than pacing would have. 1.1s leaves margin for clock skew.
MIN_INTERVAL = {
    "export.arxiv.org": 3.0,
    "api.semanticscholar.org": 1.1,
    # NCBI asks for no more than 3 requests/second without an API key.
    "eutils.ncbi.nlm.nih.gov": 0.4,
}
_last_call: dict[str, float] = {}
_pace_lock = threading.Lock()


def _pace(host: str) -> None:
    """Block until this host may be called again.

    The sleep happens while holding the lock: these limits are per-host across
    the whole process, so two worker threads must not each decide they are
    clear to go. Tool functions run in a thread pool, which is exactly when that
    would happen.
    """
    interval = MIN_INTERVAL.get(host)
    if not interval:
        return
    with _pace_lock:
        gap = time.monotonic() - _last_call.get(host, 0.0)
        if gap < interval:
            time.sleep(interval - gap)
        _last_call[host] = time.monotonic()


class FetchError(RuntimeError):
    """Network or HTTP failure, carrying enough detail to report honestly."""

    def __init__(self, message: str, status: int | None = None, host: str | None = None):
        super().__init__(message)
        self.status = status
        self.host = host


class SecurityError(RuntimeError):
    """The request was refused before it left the process."""


def _is_private(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # unparseable: treat as unsafe
    return (ip.is_private or ip.is_loopback or ip.is_link_local
            or ip.is_reserved or ip.is_multicast or ip.is_unspecified)


def assert_allowed(url: str) -> str:
    """Validate scheme, host membership, and resolved address.

    Host membership is exact-match against a frozenset. Suffix matching is
    deliberately not used: `api.crossref.org.attacker.com` ends with a trusted
    string and must still be refused.
    """
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("https", "http"):
        raise SecurityError(f"refused scheme: {parts.scheme!r}")
    host = (parts.hostname or "").lower()
    if host not in config.ALLOWED_HOSTS:
        raise SecurityError(
            f"host not in allowlist: {host!r}. This server only reaches "
            f"{', '.join(sorted(config.ALLOWED_HOSTS))}."
        )
    # DNS-rebinding / SSRF guard. Belt and braces given the allowlist, but a
    # compromised or hijacked DNS answer for an allowlisted name is exactly the
    # case the allowlist alone does not cover.
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise FetchError(f"DNS resolution failed for {host}: {e}", host=host)
    for info in infos:
        if _is_private(info[4][0]):
            raise SecurityError(
                f"{host} resolved to a private/reserved address "
                f"({info[4][0]}); refusing."
            )
    return url


def _capture_openalex_budget(host: str, headers: dict) -> None:
    """OpenAlex reports spend and remaining in response headers.

    Confirmed live 2026-09-02: OpenAlex sends X-RateLimit-Limit,
    X-RateLimit-Limit-USD, X-RateLimit-Remaining, X-RateLimit-Remaining-USD,
    X-RateLimit-Cost-USD, X-RateLimit-Credits-Used, X-RateLimit-Reset,
    X-RateLimit-Onetime-Remaining, X-RateLimit-Prepaid-Remaining-USD.

    The whole `x-ratelimit-*` family is taken, not a list of substrings: matching
    on ("budget", "spend", "remaining", ...) alone drops X-RateLimit-Limit-USD
    and X-RateLimit-Reset, which is how you end up reporting "$0.0996 remaining"
    with no denominator and no reset time. The substring list is kept as a
    fallback in case the names change again.
    """
    global _last_openalex_budget, _last_openalex_seen_at
    if host != "api.openalex.org":
        return
    found = {
        k: v for k, v in headers.items()
        if k.lower().startswith("x-ratelimit")
        or any(t in k.lower() for t in ("budget", "spend", "credit", "cost",
                                        "remaining", "usage", "quota"))
    }
    if found:
        _last_openalex_budget = found
        _last_openalex_seen_at = time.time()


def openalex_budget() -> tuple[dict[str, str], float | None]:
    return dict(_last_openalex_budget), _last_openalex_seen_at


def fetch(url: str, *, accept: str = "application/json",
          extra_headers: dict[str, str] | None = None,
          retries: int = 3) -> tuple[bytes, dict[str, str]]:
    """Fetch an allowlisted URL. Redirects are followed manually so that every
    hop is re-validated against the allowlist."""
    email = config.CONTACT_EMAIL or "unknown@example.org"
    headers = {
        "User-Agent": config.USER_AGENT_TEMPLATE.format(email=email),
        "Accept": accept,
    }
    headers.update(extra_headers or {})

    current = assert_allowed(url)
    last_exc: Exception | None = None
    started = time.monotonic()

    def _sleep_within_deadline(delay: float, host: str) -> None:
        """Back off, but never past the deadline. Three 429s honouring a long
        Retry-After can otherwise outlast the client's tool timeout, which turns
        a rate-limited source into a call that returns nothing at all rather
        than a reportable failure."""
        left = config.FETCH_DEADLINE - (time.monotonic() - started)
        if delay >= left:
            raise FetchError(
                f"{host} rate-limited or failing; giving up after "
                f"{time.monotonic() - started:.0f}s rather than exceeding the "
                f"{config.FETCH_DEADLINE:.0f}s fetch deadline", host=host)
        time.sleep(delay)

    for hop in range(config.MAX_REDIRECTS + 1):
        host = urllib.parse.urlsplit(current).hostname or ""

        _pace(host)

        for attempt in range(retries):
            try:
                req = urllib.request.Request(current, headers=headers)
                opener = urllib.request.build_opener(_NoRedirect())
                with opener.open(req, timeout=config.HTTP_TIMEOUT) as resp:
                    body = resp.read(config.MAX_RESPONSE_BYTES + 1)
                    if len(body) > config.MAX_RESPONSE_BYTES:
                        raise FetchError(
                            f"response exceeded {config.MAX_RESPONSE_BYTES} bytes "
                            f"from {host}; narrow the query", host=host)
                    hdrs = {k: v for k, v in resp.headers.items()}
                    _capture_openalex_budget(host, hdrs)
                    return body, hdrs

            except urllib.error.HTTPError as e:
                last_exc = e
                if e.code in (301, 302, 303, 307, 308):
                    loc = e.headers.get("Location")
                    if not loc:
                        raise FetchError(f"redirect without Location from {host}",
                                         status=e.code, host=host)
                    current = assert_allowed(urllib.parse.urljoin(current, loc))
                    break  # next hop
                if e.code == 429:
                    wait = e.headers.get("Retry-After")
                    delay = int(wait) if (wait or "").isdigit() else 2 ** (attempt + 1)
                    _sleep_within_deadline(min(delay, 30), host)
                    continue
                if 500 <= e.code < 600:
                    _sleep_within_deadline(2 ** attempt, host)
                    continue
                detail = ""
                try:
                    detail = e.read(500).decode("utf-8", "replace")
                except Exception:
                    pass
                raise FetchError(f"HTTP {e.code} from {host}: {detail[:200]}",
                                 status=e.code, host=host)

            except (urllib.error.URLError, TimeoutError, socket.timeout) as e:
                last_exc = e
                _sleep_within_deadline(2 ** attempt, host)
        else:
            raise FetchError(f"{host} unreachable after {retries} attempts: {last_exc}",
                             host=host)

    raise FetchError(f"too many redirects (>{config.MAX_REDIRECTS})")


def fetch_json(url: str, **kw) -> Any:
    body, _ = fetch(url, **kw)
    try:
        return json.loads(body)
    except json.JSONDecodeError as e:
        host = urllib.parse.urlsplit(url).hostname
        raise FetchError(f"non-JSON response from {host}: {e}", host=host)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Surface redirects as HTTPError so fetch() can re-validate each hop
    instead of letting urllib follow them to an unvalidated host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def build_url(host: str, path: str, params: dict[str, Any] | None = None) -> str:
    """Construct an allowlisted URL. The only way URLs are made in this server.

    `path` is quoted, so a DOI containing `/` stays inside one path segment and
    cannot introduce query parameters.
    """
    if host not in config.ALLOWED_HOSTS:
        raise SecurityError(f"refusing to build URL for non-allowlisted host {host!r}")
    clean = {k: v for k, v in (params or {}).items() if v not in (None, "", [])}
    query = urllib.parse.urlencode(clean, doseq=True, quote_via=urllib.parse.quote)
    safe_path = urllib.parse.quote(path.lstrip("/"), safe="/:")
    return f"https://{host}/{safe_path}" + (f"?{query}" if query else "")
