"""Configuration and the security allowlist.

The allowlist is the primary defense. See identity.md, "What the server must
never do" — every URL this server fetches is built here or in sources.py from
validated parameters. Nothing accepts a caller-supplied URL.
"""
import os
import re

# Exact hostnames only. Suffix matching would let
# `api.crossref.org.attacker.com` through, so membership is tested with `in`,
# never with endswith().
ALLOWED_HOSTS = frozenset({
    "api.openalex.org",
    "api.crossref.org",
    "api.semanticscholar.org",
    "api.unpaywall.org",
    "export.arxiv.org",
    "www.ebi.ac.uk",          # Europe PMC
    "api.datacite.org",
})

CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", "").strip()
OPENALEX_API_KEY = os.environ.get("OPENALEX_API_KEY", "").strip()
S2_API_KEY = os.environ.get("S2_API_KEY", "").strip()
MCP_AUTH_TOKEN = os.environ.get("MCP_AUTH_TOKEN", "").strip()

# The public hostname this server is reached on. The MCP transport validates the
# Host header against this (DNS-rebinding protection); if it is wrong or unset,
# every /mcp request is answered 421 while /health still returns 200 — a healthy
# deploy in front of a dead server. Railway injects RAILWAY_PUBLIC_DOMAIN, so the
# common case needs no configuration.
PUBLIC_HOSTNAME = (os.environ.get("PUBLIC_HOSTNAME", "").strip()
                   or os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip())

PORT = int(os.environ.get("PORT", "8000"))
HOST = os.environ.get("HOST", "0.0.0.0")

CACHE_PATH = os.environ.get("CACHE_PATH", "/tmp/scholarly_cache.sqlite")
CACHE_TTL_SECONDS = int(os.environ.get("CACHE_TTL_SECONDS", str(7 * 24 * 3600)))

HTTP_TIMEOUT = float(os.environ.get("HTTP_TIMEOUT", "25"))
# Ceiling on one fetch INCLUDING retry backoff. Three 429s with a generous
# Retry-After could otherwise outlast the client's tool timeout, turning one
# rate-limited source into a dead call with no result at all.
FETCH_DEADLINE = float(os.environ.get("FETCH_DEADLINE", "45"))
MAX_RESPONSE_BYTES = int(os.environ.get("MAX_RESPONSE_BYTES", str(8 * 1024 * 1024)))
MAX_REDIRECTS = 3

USER_AGENT_TEMPLATE = (
    "scholarly-mcp/1.0 (+https://github.com/; mailto:{email}) "
    "python-urllib"
)

# DOIs are `10.<registrant>/<suffix>`. Anchored, and the suffix excludes
# characters that would let a caller escape the path segment or add query
# parameters to a URL we construct.
DOI_RE = re.compile(r"^10\.\d{4,9}/[^\s?#&\\]+$")

# A DOI suffix may legitimately contain "/", so the regex alone does not stop
# `10.1234/../../v2/x` from walking up to a different endpoint on an allowlisted
# host. Segments after the registrant are checked against this set.
DOI_BAD_SEGMENTS = frozenset({"", ".", ".."})

ARXIV_ID_RE = re.compile(r"^\d{4}\.\d{4,5}(v\d+)?$|^[a-z-]+(\.[A-Z]{2})?/\d{7}(v\d+)?$")


class ConfigError(RuntimeError):
    pass


def require_email() -> str:
    """Crossref, Unpaywall and arXiv all expect contact info; Crossref's polite
    pool depends on it. Failing loudly at startup beats being rate-limited into
    partial results that look complete."""
    if not CONTACT_EMAIL or "@" not in CONTACT_EMAIL:
        raise ConfigError(
            "CONTACT_EMAIL must be set to a real address. Crossref, Unpaywall "
            "and arXiv expect it, and Crossref's polite pool depends on it."
        )
    return CONTACT_EMAIL


def allowed_http_hosts() -> list[str]:
    """Host header values the MCP transport will accept.

    Both the bare hostname and a `:*` port pattern are needed: a proxy may or may
    not append the port. Empty means we do not know the public hostname, and the
    caller must decide what to do about that rather than guessing.
    """
    hosts = ["localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*", "[::1]:*"]
    if PUBLIC_HOSTNAME:
        hosts = [PUBLIC_HOSTNAME, f"{PUBLIC_HOSTNAME}:*"] + hosts
    return hosts


def startup_report() -> dict:
    return {
        "contact_email_set": bool(CONTACT_EMAIL and "@" in CONTACT_EMAIL),
        "openalex_key_set": bool(OPENALEX_API_KEY),
        "openalex_daily_budget": "$1.00" if OPENALEX_API_KEY else "$0.10 (no key)",
        "s2_key_set": bool(S2_API_KEY),
        "auth_required": bool(MCP_AUTH_TOKEN),
        "public_hostname": PUBLIC_HOSTNAME or None,
        "mcp_allowed_host_headers": allowed_http_hosts() if PUBLIC_HOSTNAME else None,
        "dns_rebinding_protection": bool(PUBLIC_HOSTNAME),
        "allowed_hosts": sorted(ALLOWED_HOSTS),
        "cache_path": CACHE_PATH,
    }
