"""Offline tests. No network required — run these anywhere.

The allowlist and DOI-validation tests are the important ones: they encode the
security invariants from identity.md. If one of them starts failing, the server
has become the confused-deputy passthrough it was designed not to be.

    python -m pytest tests/ -v        (or: python -m tests.test_offline)
"""
import os
import sys
import unittest

os.environ.setdefault("CONTACT_EMAIL", "test@example.org")
os.environ.setdefault("CACHE_PATH", "/tmp/test_scholarly_cache.sqlite")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import merge, sources  # noqa: E402
from app.http import SecurityError, assert_allowed, build_url  # noqa: E402


class TestAllowlist(unittest.TestCase):
    """The primary defense. See identity.md, rules 1-3."""

    def test_allowed_hosts_pass(self):
        for host in ("api.crossref.org", "api.openalex.org", "api.unpaywall.org"):
            assert_allowed(f"https://{host}/works")

    def test_suffix_attack_refused(self):
        """The reason membership is `in frozenset`, never endswith()."""
        for evil in (
            "https://api.crossref.org.attacker.com/works",
            "https://evil.com/api.crossref.org",
            "https://api.crossref.org.evil.io/x",
        ):
            with self.assertRaises(SecurityError, msg=f"allowed {evil}"):
                assert_allowed(evil)

    def test_unlisted_host_refused(self):
        for evil in ("https://scholar.google.com/x", "https://attacker.io/collect"):
            with self.assertRaises(SecurityError):
                assert_allowed(evil)

    def test_metadata_endpoint_refused(self):
        """Classic SSRF target. Blocked by the allowlist before the IP guard."""
        for evil in ("http://169.254.169.254/latest/meta-data/",
                     "http://127.0.0.1:8000/mcp",
                     "http://localhost/admin",
                     "http://[::1]/x"):
            with self.assertRaises(SecurityError):
                assert_allowed(evil)

    def test_non_http_scheme_refused(self):
        for evil in ("file:///etc/passwd", "gopher://x/", "ftp://api.crossref.org/x"):
            with self.assertRaises(SecurityError):
                assert_allowed(evil)

    def test_build_url_refuses_unlisted_host(self):
        with self.assertRaises(SecurityError):
            build_url("attacker.io", "collect", {"key": "secret"})


class TestBuildUrl(unittest.TestCase):
    def test_params_encoded(self):
        url = build_url("api.crossref.org", "works",
                        {"query.bibliographic": "a b&c", "rows": 5})
        self.assertIn("api.crossref.org/works?", url)
        self.assertNotIn(" ", url)
        self.assertIn("rows=5", url)

    def test_empty_params_dropped(self):
        url = build_url("api.crossref.org", "works", {"a": "x", "b": None, "c": ""})
        self.assertIn("a=x", url)
        self.assertNotIn("b=", url)

    def test_doi_stays_in_path(self):
        """A DOI's slash must not create a new path segment that escapes."""
        url = build_url("api.crossref.org", "works/10.1038/nature12373", {})
        self.assertTrue(url.startswith("https://api.crossref.org/works/10.1038/"))


class TestDoiValidation(unittest.TestCase):
    def test_accepts_valid(self):
        for raw, want in (
            ("10.1038/nature12373", "10.1038/nature12373"),
            ("https://doi.org/10.1038/NATURE12373", "10.1038/nature12373"),
            ("doi:10.1000/xyz.2020", "10.1000/xyz.2020"),
            ("10.1038/nature12373.", "10.1038/nature12373"),
        ):
            self.assertEqual(sources.validate_doi(raw), want)

    def test_rejects_injection(self):
        """Suffix characters that could add query params or escape the path."""
        for evil in (
            "10.1038/x?api_key=leak",
            "10.1038/x#frag",
            "10.1038/x&mailto=attacker",
            "not-a-doi",
            "../../../etc/passwd",
            "10.1/x y",
            "",
        ):
            with self.assertRaises(ValueError, msg=f"accepted {evil!r}"):
                sources.validate_doi(evil)


class TestMerge(unittest.TestCase):
    def _rec(self, src, **kw):
        r = {"doi": None, "title": None, "year": None, "authors": [],
             "cited_by_count": None, "found_by": [src]}
        r.update(kw)
        r["found_by"] = [src]
        return r

    def test_dedup_by_doi_case_and_prefix(self):
        m = merge.merge([
            self._rec("openalex", doi="https://doi.org/10.1038/NATURE12373", title="A"),
            self._rec("crossref", doi="10.1038/nature12373", title="A"),
        ])
        self.assertEqual(len(m), 1)
        self.assertEqual(m[0]["corroboration"], 2)

    def test_dedup_by_title_with_year_drift(self):
        """Indexes disagree about online-first vs issue dates constantly."""
        m = merge.merge([
            self._rec("arxiv", title="Deep Learning: A Review", year=2013),
            self._rec("semanticscholar", title="deep learning, a review!", year=2014),
        ])
        self.assertEqual(len(m), 1)

    def test_distinct_papers_not_merged(self):
        m = merge.merge([
            self._rec("openalex", title="Paper One", year=2020),
            self._rec("openalex", title="Paper Two", year=2020),
        ])
        self.assertEqual(len(m), 2)

    def test_openalex_and_unpaywall_are_not_independent(self):
        """They share the same OA dataset — agreement is not corroboration."""
        self.assertEqual(merge.independent_count(["openalex", "unpaywall"]), 1)
        self.assertEqual(merge.independent_count(["openalex", "crossref"]), 2)

    def test_absorb_fills_missing_fields(self):
        m = merge.merge([
            self._rec("openalex", doi="10.1/x", title="T", year=None),
            self._rec("crossref", doi="10.1/x", title="T", year=2020,
                      authors=["A B"]),
        ])
        self.assertEqual(m[0]["year"], 2020)
        self.assertEqual(m[0]["authors"], ["A B"])


class TestRetractionClassification(unittest.TestCase):
    def test_retraction(self):
        status, notes = sources.classify_updates(
            {"update-to": [{"type": "retraction", "DOI": "10.1/r", "label": "Retraction"}]})
        self.assertEqual(status, "retracted")
        self.assertTrue(notes)

    def test_expression_of_concern_not_retraction(self):
        """The distinction OpenAlex's boolean cannot make."""
        status, _ = sources.classify_updates(
            {"update-to": [{"type": "expression_of_concern", "DOI": "10.1/e"}]})
        self.assertEqual(status, "concern")

    def test_correction_is_not_retraction(self):
        status, _ = sources.classify_updates(
            {"update-to": [{"type": "correction", "DOI": "10.1/c"}]})
        self.assertEqual(status, "corrected")

    def test_retraction_wins_over_correction(self):
        status, _ = sources.classify_updates({"update-to": [
            {"type": "correction", "DOI": "10.1/c"},
            {"type": "retraction", "DOI": "10.1/r"},
        ]})
        self.assertEqual(status, "retracted")

    def test_clean_record(self):
        self.assertEqual(sources.classify_updates({})[0], "ok")


class TestNormalization(unittest.TestCase):
    def test_title_normalization_strips_noise(self):
        self.assertEqual(sources.norm_title("The Deep Learning: A Review!"),
                         sources.norm_title("deep learning  review"))

    def test_unicode_folded(self):
        self.assertEqual(sources.norm_title("Schrödinger"),
                         sources.norm_title("Schrodinger"))


class TestToolsRegistered(unittest.TestCase):
    def test_five_tools_present(self):
        from app.server import mcp
        import asyncio
        tools = asyncio.run(mcp.list_tools())
        names = {t.name for t in tools}
        self.assertEqual(names, {"search_literature", "verify_doi",
                                 "expand_citations", "resolve_fulltext",
                                 "budget_status"})

    def test_no_generic_url_tool(self):
        """identity.md rule 1: no tool may accept a caller-supplied URL."""
        from app.server import mcp
        import asyncio, json
        tools = asyncio.run(mcp.list_tools())
        for t in tools:
            schema = json.dumps(getattr(t, "input_schema", None)
                                or getattr(t, "inputSchema", {})).lower()
            for banned in ('"url"', '"endpoint"', '"host"', '"headers"'):
                self.assertNotIn(banned, schema,
                                 f"tool {t.name} exposes {banned} — that is the "
                                 f"passthrough shape identity.md rejects")


class TestDoiPathTraversal(unittest.TestCase):
    """A DOI suffix may contain "/", and build_url keeps "/" unescaped, so the
    anchored regex alone still admitted `10.1234/../../v2/x` — a URL that
    resolves to a different endpoint on an allowlisted host."""

    def test_rejects_relative_segments(self):
        for evil in (
            "10.1234/../../v2/admin",
            "10.1234/a/../../b",
            "10.1234/../../../etc/passwd",
            "10.1234/./x",
            "10.1234/a//b",
        ):
            with self.assertRaises(ValueError, msg=f"accepted {evil!r}"):
                sources.validate_doi(evil)

    def test_still_accepts_multi_segment_dois(self):
        """Real DOIs do contain slashes; the fix must not reject them."""
        self.assertEqual(sources.validate_doi("10.1007/978-3-031-84300-6_13"),
                         "10.1007/978-3-031-84300-6_13")
        self.assertEqual(sources.validate_doi("10.1016/S0140-6736(97)11096-0"),
                         "10.1016/s0140-6736(97)11096-0")

    def test_built_url_has_no_traversal(self):
        for raw in ("10.1234/../../v2/admin", "10.1234/a/../b"):
            with self.assertRaises(ValueError):
                build_url("api.crossref.org",
                          f"works/{sources.validate_doi(raw)}", {})


class TestRetractionFieldDirection(unittest.TestCase):
    """Crossref puts `update-to` on the retraction NOTICE and `updated-by` on the
    retracted PAPER. Reading only `update-to` classified every retracted paper as
    clean. Shapes below are copied from live Crossref responses."""

    def test_updated_by_retraction_is_detected(self):
        """Wakefield 1998 (10.1016/S0140-6736(97)11096-0) has exactly this shape:
        update-to absent, updated-by carrying a correction then a retraction."""
        msg = {"updated-by": [
            {"DOI": "10.1016/s0140-6736(04)15715-2", "type": "correction",
             "label": "Correction", "source": "retraction-watch"},
            {"DOI": "10.1016/s0140-6736(10)60175-4", "type": "retraction",
             "label": "Retraction", "source": "retraction-watch"},
        ]}
        status, notes = sources.classify_updates(msg)
        self.assertEqual(status, "retracted")
        self.assertEqual(len(notes), 2)

    def test_updated_by_expression_of_concern(self):
        msg = {"updated-by": [{"DOI": "10.1056/nejme2020822",
                               "type": "expression_of_concern",
                               "label": "Expression of concern"}]}
        self.assertEqual(sources.classify_updates(msg)[0], "concern")

    def test_update_to_still_read(self):
        """A record that IS a notice still classifies from update-to."""
        msg = {"update-to": [{"DOI": "10.1/r", "type": "retraction"}]}
        self.assertEqual(sources.classify_updates(msg)[0], "retracted")

    def test_severity_not_order_dependent(self):
        """A correction listed before an expression of concern must not swallow
        it. Live records list updates in deposit order, not severity order."""
        msg = {"updated-by": [
            {"DOI": "10.1/c", "type": "correction"},
            {"DOI": "10.1/e", "type": "expression_of_concern"},
        ]}
        self.assertEqual(sources.classify_updates(msg)[0], "concern")

    def test_retraction_beats_everything_regardless_of_order(self):
        for order in (["retraction", "correction", "expression_of_concern"],
                      ["expression_of_concern", "correction", "retraction"],
                      ["correction", "retraction", "expression_of_concern"]):
            msg = {"updated-by": [{"DOI": "10.1/x", "type": t} for t in order]}
            self.assertEqual(sources.classify_updates(msg)[0], "retracted",
                             f"order {order} lost the retraction")

    def test_clean_paper_stays_ok(self):
        self.assertEqual(sources.classify_updates({})[0], "ok")
        self.assertEqual(sources.classify_updates({"updated-by": []})[0], "ok")


class TestHostHeaderValidation(unittest.TestCase):
    """Omitting `host=` from streamable_http_app() makes the SDK auto-enable
    DNS-rebinding protection for localhost only, so every request arriving on a
    real domain is answered 421 while /health still returns 200."""

    def test_public_hostname_is_accepted(self):
        from app import config, main
        orig = config.PUBLIC_HOSTNAME
        try:
            config.PUBLIC_HOSTNAME = "scholarly-mcp.up.railway.app"
            self.assertTrue(main._host_accepted("scholarly-mcp.up.railway.app"))
            self.assertTrue(main._host_accepted("scholarly-mcp.up.railway.app:443"))
            self.assertTrue(main._host_accepted("localhost:8000"))
            self.assertFalse(main._host_accepted("attacker.example.com"))
            self.assertFalse(main._host_accepted(None))
        finally:
            config.PUBLIC_HOSTNAME = orig

    def test_allowed_hosts_include_bare_and_port_forms(self):
        from app import config
        orig = config.PUBLIC_HOSTNAME
        try:
            config.PUBLIC_HOSTNAME = "example.org"
            hosts = config.allowed_http_hosts()
            self.assertIn("example.org", hosts)
            self.assertIn("example.org:*", hosts)
        finally:
            config.PUBLIC_HOSTNAME = orig


class TestBudgetHeaderCapture(unittest.TestCase):
    """Real header names, confirmed live 2026-09-02. The old substring list
    dropped X-RateLimit-Limit-USD and X-RateLimit-Reset, leaving budget_status
    reporting an amount remaining with no denominator and no reset time."""

    def test_captures_full_ratelimit_family(self):
        from app import http as apphttp
        apphttp._last_openalex_budget = {}
        apphttp._capture_openalex_budget("api.openalex.org", {
            "X-RateLimit-Limit": "1000",
            "X-RateLimit-Limit-USD": "0.1",
            "X-RateLimit-Remaining": "996",
            "X-RateLimit-Remaining-USD": "0.0996",
            "X-RateLimit-Reset": "58220",
            "Content-Type": "application/json",
        })
        got, _ = apphttp.openalex_budget()
        for k in ("X-RateLimit-Limit-USD", "X-RateLimit-Reset",
                  "X-RateLimit-Remaining-USD", "X-RateLimit-Limit"):
            self.assertIn(k, got, f"dropped {k}")
        self.assertNotIn("Content-Type", got)

    def test_ignores_non_openalex_hosts(self):
        from app import http as apphttp
        apphttp._last_openalex_budget = {}
        apphttp._capture_openalex_budget("api.crossref.org",
                                         {"X-RateLimit-Limit": "1"})
        self.assertEqual(apphttp.openalex_budget()[0], {})


class TestCacheThreadSafety(unittest.TestCase):
    """sqlite3.threadsafety is 1 on common CPython builds: connections must not
    be shared across threads. The SDK runs sync tools via anyio.to_thread, and
    the connection is opened check_same_thread=False, so only the lock stops it."""

    def test_concurrent_cache_access(self):
        import threading
        errors = []

        def worker(n):
            try:
                for i in range(25):
                    merge.cached(f"concurrent:{n}:{i}", lambda: {"n": n, "i": i},
                                 ttl=600)
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [], f"concurrent cache access raised: {errors}")

    def test_uncacheable_value_still_returned(self):
        sentinel = object()
        self.assertIs(merge.cached("uncacheable", lambda: sentinel), sentinel)


class TestDisputedFlagGuidance(unittest.TestCase):
    """Every publication_status that is not "ok" must carry a guidance line.
    "disputed_flag" was reachable but absent from the guidance chain, so the
    highest-ambiguity case returned no instruction at all."""

    def test_all_non_ok_statuses_have_guidance(self):
        import inspect
        from app import server
        src = inspect.getsource(server.verify_doi.fn
                                if hasattr(server.verify_doi, "fn")
                                else server.verify_doi)
        for status in ("disputed_flag", "retracted", "concern", "corrected"):
            self.assertIn(f'"{status}"', src,
                          f"{status} has no branch in verify_doi")


if __name__ == "__main__":
    unittest.main(verbosity=2)
