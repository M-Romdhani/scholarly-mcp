"""Deduplication across indexes, and a small on-disk cache.

Corroboration — how many *independent* indexes found a paper — is the signal
that survives merging, so it is computed here rather than inferred later.
"""
import json
import sqlite3
import threading
import time
from typing import Any, Callable

from . import config
from .sources import norm_doi, norm_title

# OpenAlex incorporates the same open-access dataset as Unpaywall, so agreement
# between those two is not independent evidence. Indexes in the same group count
# once toward corroboration.
INDEPENDENCE_GROUPS = {
    "openalex": "openalex",
    "unpaywall": "openalex",
    "crossref": "crossref",
    "semanticscholar": "semanticscholar",
    "arxiv": "arxiv",
}


def independent_count(found_by: list[str]) -> int:
    return len({INDEPENDENCE_GROUPS.get(s, s) for s in found_by})


def merge(records: list[dict]) -> list[dict]:
    """Dedup by normalized DOI, then by normalized title + year (+/-1 year, since
    indexes disagree about online-first vs issue dates constantly)."""
    by_doi: dict[str, dict] = {}
    by_title: dict[tuple, dict] = {}
    out: list[dict] = []

    def absorb(dst: dict, src: dict) -> None:
        for s in src.get("found_by", []):
            if s not in dst["found_by"]:
                dst["found_by"].append(s)
        for k, v in src.items():
            if k == "found_by":
                continue
            if dst.get(k) in (None, "", []) and v not in (None, "", []):
                dst[k] = v

    for r in records:
        doi = norm_doi(r.get("doi"))
        if doi and doi in by_doi:
            absorb(by_doi[doi], r)
            continue
        tkey = norm_title(r.get("title"))
        year = r.get("year")
        hit = None
        if tkey:
            for y in (year, (year or 0) + 1, (year or 0) - 1):
                if (tkey, y) in by_title:
                    hit = by_title[(tkey, y)]
                    break
        if hit is not None:
            absorb(hit, r)
            if doi:
                by_doi[doi] = hit
            continue
        rec = dict(r)
        rec["found_by"] = list(r.get("found_by", []))
        out.append(rec)
        if doi:
            by_doi[doi] = rec
        if tkey:
            by_title[(tkey, year)] = rec

    for rec in out:
        rec["corroboration"] = independent_count(rec["found_by"])
    return out


# ------------------------------------------------------------------ cache

_conn: sqlite3.Connection | None = None

# The MCP SDK runs sync tool functions in a worker thread pool
# (anyio.to_thread.run_sync), so two tool calls can touch this connection at the
# same time. CPython reports sqlite3.threadsafety == 1 on the common builds:
# module-level only, connections must NOT be shared between threads. The
# connection is opened with check_same_thread=False, so nothing stops that
# sharing except this lock.
_lock = threading.Lock()


def _db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(config.CACHE_PATH, check_same_thread=False)
        _conn.execute(
            "CREATE TABLE IF NOT EXISTS cache "
            "(k TEXT PRIMARY KEY, v TEXT NOT NULL, ts REAL NOT NULL)"
        )
        _conn.commit()
    return _conn


def cached(key: str, producer: Callable[[], Any], ttl: int | None = None) -> Any:
    """Cache a JSON-serializable result.

    Citation expansion revisits the same DOIs across search rounds, so this
    pays for itself immediately. Failures are never cached — a transient 503
    must not become a persistent wrong answer.
    """
    ttl = config.CACHE_TTL_SECONDS if ttl is None else ttl
    try:
        with _lock:
            db = _db()
            row = db.execute("SELECT v, ts FROM cache WHERE k = ?", (key,)).fetchone()
        if row and (time.time() - row[1]) < ttl:
            return json.loads(row[0])
    except (sqlite3.Error, json.JSONDecodeError):
        pass

    # Deliberately outside the lock: this is a network call taking seconds, and
    # holding the cache lock across it would serialize every concurrent tool call.
    value = producer()

    try:
        payload = json.dumps(value)
    except TypeError:
        return value  # not cacheable; still a valid result
    try:
        with _lock:
            db = _db()
            db.execute("INSERT OR REPLACE INTO cache (k, v, ts) VALUES (?, ?, ?)",
                       (key, payload, time.time()))
            db.commit()
    except sqlite3.Error:
        pass  # cache is best-effort; never fail a request over it
    return value


def cache_stats() -> dict:
    try:
        with _lock:
            db = _db()
            n = db.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
            oldest = db.execute("SELECT MIN(ts) FROM cache").fetchone()[0]
        return {"entries": n, "oldest_age_seconds":
                round(time.time() - oldest) if oldest else None}
    except sqlite3.Error as e:
        return {"error": str(e)}
