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
    def test_tools_present(self):
        from app.server import mcp
        import asyncio
        tools = asyncio.run(mcp.list_tools())
        names = {t.name for t in tools}
        self.assertEqual(names, {"search_literature", "verify_doi",
                                 "expand_citations", "resolve_fulltext",
                                 "fetch_fulltext", "budget_status"})

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


class TestRelevanceRanking(unittest.TestCase):
    """Sorting merged results on citation count alone surfaced clinical
    guidelines and burden-of-disease reviews (8,000+ citations) above the
    pivotal randomised trial the query was actually about. Each index's own
    relevance rank has to survive the merge."""

    def _rec(self, src, doi, rank, cites, corr=None):
        r = {"doi": doi, "title": doi, "year": 2020, "found_by": [src],
             "source_rank": rank, "cited_by_count": cites}
        if corr is not None:
            r["corroboration"] = corr
        return r

    def test_relevance_beats_raw_citation_count(self):
        on_topic = self._rec("openalex", "10.1/trial", 0, 200, corr=1)
        off_topic = self._rec("openalex", "10.1/guideline", 20, 9000, corr=1)
        ordered = sorted([off_topic, on_topic], key=merge.relevance_key)
        self.assertEqual(ordered[0]["doi"], "10.1/trial")

    def test_corroboration_breaks_ties_at_equal_relevance(self):
        corroborated = self._rec("openalex", "10.1/two", 3, 10, corr=2)
        single = self._rec("openalex", "10.1/one", 3, 10, corr=1)
        ordered = sorted([single, corroborated], key=merge.relevance_key)
        self.assertEqual(ordered[0]["doi"], "10.1/two")

    def test_corroboration_does_not_outrank_relevance(self):
        """Indexes agree readily on broad topical matches, so a corroborated but
        off-topic paper must not displace the on-topic one. On a cardiovascular
        query this ordering had put breast cancer and diabetes papers above the
        pivotal trial."""
        off_topic_corroborated = self._rec("openalex", "10.1/breastcancer", 1, 43, corr=2)
        on_topic = self._rec("openalex", "10.1/predimed", 0, 3599, corr=1)
        ordered = sorted([off_topic_corroborated, on_topic], key=merge.relevance_key)
        self.assertEqual(ordered[0]["doi"], "10.1/predimed")

    def test_unranked_sorts_behind_ranked(self):
        ranked = self._rec("openalex", "10.1/ranked", 40, 0, corr=1)
        unranked = self._rec("openalex", "10.1/unranked", None, 999, corr=1)
        unranked.pop("source_rank")
        ordered = sorted([unranked, ranked], key=merge.relevance_key)
        self.assertEqual(ordered[0]["doi"], "10.1/ranked")

    def test_merge_keeps_best_rank_across_indexes(self):
        m = merge.merge([
            {"doi": "10.1/x", "title": "T", "year": 2020, "found_by": ["openalex"],
             "source_rank": 18, "cited_by_count": 5},
            {"doi": "10.1/x", "title": "T", "year": 2020, "found_by": ["crossref"],
             "source_rank": 2, "cited_by_count": 5},
        ])
        self.assertEqual(len(m), 1)
        self.assertEqual(m[0]["source_rank"], 2,
                         "merge must keep the best rank any index gave it")


class TestFullTextRoutes(unittest.TestCase):
    """Europe PMC and NCBI gate the same PMC corpus differently: EPMC's
    isOpenAccess flag is stricter than "readable" and refuses records NCBI serves
    in full. Measured on three papers EPMC declined, NCBI returned 34 and 40 body
    paragraphs for two."""

    def test_ncbi_url_built_from_validated_pmcid(self):
        for bad in ("../../etc", "PMC", "49066", "PMC1; DROP", ""):
            with self.assertRaises(ValueError, msg=f"accepted {bad!r}"):
                sources.ncbi_pmc_fulltext(bad)

    def test_ncbi_host_allowlisted(self):
        assert_allowed("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi")

    def test_jats_parser_shared_by_both_routes(self):
        """NCBI wraps the article in <pmc-articleset>; the body is identical."""
        import xml.etree.ElementTree as ET
        wrapped = ET.fromstring(
            "<pmc-articleset><article><body><sec><title>Results</title>"
            "<p>Found it.</p></sec></body></article></pmc-articleset>")
        parsed = sources._parse_jats(wrapped.find(".//article"))
        self.assertEqual([x["heading"] for x in parsed["sections"]], ["Results"])


class TestAbstractOnlyIsNotFullText(unittest.TestCase):
    """A PMC record for a pre-XML article returns an abstract and no body.
    Reporting that as retrieved would let a caller record access as 'fulltext'
    having read only an abstract — the inflation identity.md rule 5 forbids."""

    def test_body_detection_excludes_abstract(self):
        sections = [{"heading": "Abstract", "text": "a"}]
        body = [x for x in sections
                if x["heading"].strip().lower() != "abstract"]
        self.assertEqual(body, [], "abstract alone must not count as body text")

    def test_body_detection_accepts_real_sections(self):
        sections = [{"heading": "Abstract", "text": "a"},
                    {"heading": "Results", "text": "b"}]
        body = [x for x in sections
                if x["heading"].strip().lower() != "abstract"]
        self.assertEqual(len(body), 1)

    def test_abstract_only_branch_present_in_tool(self):
        import inspect
        from app import server
        src = inspect.getsource(server.fetch_fulltext.fn
                                if hasattr(server.fetch_fulltext, "fn")
                                else server.fetch_fulltext)
        self.assertIn('"abstract_only"', src)
        self.assertIn("abstract-only", src)


class TestOpenAlexQuerySanitising(unittest.TestCase):
    """OpenAlex answers HTTP 400 when * or ? appear in a search string; tested
    against the live API, every other punctuation character passes. Entities are
    sometimes named with them — "Aβ*56" is a real molecule name — so searching
    for the thing by its actual name crashed the call."""

    def test_wildcards_removed(self):
        self.assertEqual(sources._oa_query("Abeta*56 oligomer"), "Abeta 56 oligomer")
        self.assertEqual(sources._oa_query("what? oligomer"), "what oligomer")

    def test_other_punctuation_preserved(self):
        q = 'amyloid-beta (1-42) "oligomer": a review/analysis'
        self.assertEqual(sources._oa_query(q), q)

    def test_collapses_resulting_whitespace(self):
        self.assertEqual(sources._oa_query("a * ? b"), "a b")


class TestRetractionScreen(unittest.TestCase):
    """A screen that ran and found nothing and a screen that never ran emit
    identical output when only the absence of hits is reported, so there is
    nothing to audit the null against. The count of what was examined travels
    with the result, and so does the positive control."""

    def _screen(self, records):
        from app import server
        return server._retraction_screen(records)

    def test_flags_openalex_is_retracted(self):
        s = self._screen([{"doi": "10.1/r", "title": "T", "is_retracted": True},
                          {"doi": "10.1/ok", "title": "U", "is_retracted": False}])
        self.assertEqual(s["flagged_count"], 1)
        self.assertEqual(s["flagged"][0]["doi"], "10.1/r")

    def test_flags_medline_retracted_publication(self):
        s = self._screen([{"doi": "10.1/r", "title": "T",
                           "pub_types": ["Retracted Publication", "Journal Article"]}])
        self.assertEqual(s["flagged_count"], 1)
        self.assertEqual(s["flagged"][0]["medline_publication_types"],
                         ["Retracted Publication"])

    def test_unknown_status_is_not_flagged(self):
        """is_retracted=None means the index did not say, which is not a flag."""
        self.assertEqual(self._screen([{"doi": "10.1/x", "is_retracted": None}])
                         ["flagged_count"], 0)

    def test_block_is_present_even_when_nothing_flagged(self):
        """The whole point: a clean screen must still report itself."""
        s = self._screen([{"doi": "10.1/a", "is_retracted": False}])
        self.assertEqual(s["records_screened"], 1)
        self.assertEqual(s["flagged_count"], 0)
        self.assertIn("interpretation", s)

    def test_denominator_counts_records_carrying_the_field(self):
        s = self._screen([
            {"doi": "10.1/a", "is_retracted": False},          # has the field
            {"doi": "10.1/b", "pub_types": ["Journal Article"]},  # has the field
            {"doi": "10.1/c"},                                  # does not
        ])
        self.assertEqual(s["records_screened"], 3)
        self.assertEqual(s["records_carrying_status_data"], 2)

    def test_crossref_status_counts_as_status_data(self):
        """Crossref returns updated-by on search results and the adapter now
        carries it, so a Crossref-only search is a real screen rather than an
        uninformative one."""
        s = self._screen([{"doi": "10.1/a", "crossref_status": "ok"},
                          {"doi": "10.1/b", "crossref_status": "retracted"}])
        self.assertEqual(s["records_carrying_status_data"], 2)
        self.assertEqual(s["flagged_count"], 1)
        self.assertEqual(s["flagged"][0]["crossref_status"], "retracted")

    def test_crossref_concern_is_flagged(self):
        s = self._screen([{"doi": "10.1/c", "crossref_status": "concern"}])
        self.assertEqual(s["flagged_count"], 1)

    def test_crossref_corrected_is_not_flagged_but_counts_as_checked(self):
        """A correction is not a retraction; the record was still screened."""
        s = self._screen([{"doi": "10.1/d", "crossref_status": "corrected"}])
        self.assertEqual(s["flagged_count"], 0)
        self.assertEqual(s["records_carrying_status_data"], 1)

    def test_no_status_data_reads_as_uninformative_not_clean(self):
        """Zero hits AND zero records carrying the field is the signature of a
        check that could not have worked. It must not read as a clean result."""
        s = self._screen([{"doi": "10.1/x"}, {"doi": "10.1/y"}])
        self.assertEqual(s["records_carrying_status_data"], 0)
        self.assertIn("UNINFORMATIVE", s["interpretation"])
        self.assertNotIn("real negative", s["interpretation"])

    def test_clean_screen_says_it_is_a_real_negative(self):
        s = self._screen([{"doi": "10.1/a", "is_retracted": False},
                          {"doi": "10.1/b", "is_retracted": False}])
        self.assertIn("real negative", s["interpretation"])

    def test_empty_result_set_is_not_called_uninformative(self):
        s = self._screen([])
        self.assertEqual(s["records_screened"], 0)
        self.assertNotIn("UNINFORMATIVE", s.get("interpretation", ""))


class TestRequestPacing(unittest.TestCase):
    """Semantic Scholar issues keys limited to 1 request/second cumulative
    across all endpoints, so search and citation calls share one budget."""

    def test_semanticscholar_is_paced(self):
        from app import http as apphttp
        self.assertIn("api.semanticscholar.org", apphttp.MIN_INTERVAL)
        self.assertGreaterEqual(apphttp.MIN_INTERVAL["api.semanticscholar.org"], 1.0)

    def test_arxiv_still_paced(self):
        from app import http as apphttp
        self.assertGreaterEqual(apphttp.MIN_INTERVAL["export.arxiv.org"], 3.0)

    def test_pacing_actually_delays(self):
        import time
        from app import http as apphttp
        apphttp._last_call.pop("api.semanticscholar.org", None)
        apphttp._pace("api.semanticscholar.org")
        start = time.monotonic()
        apphttp._pace("api.semanticscholar.org")
        self.assertGreaterEqual(time.monotonic() - start, 1.0)

    def test_unpaced_host_is_not_delayed(self):
        import time
        from app import http as apphttp
        start = time.monotonic()
        apphttp._pace("api.crossref.org")
        self.assertLess(time.monotonic() - start, 0.5)


class TestOriginValidation(unittest.TestCase):
    """The MCP transport answers 403 to any Origin not on the allow list. Left at
    just the server's own hostname, Claude's connector — the client this exists to
    serve — was rejected with an opaque 403 that reads like an auth failure."""

    def test_claude_origins_allowed(self):
        from app import config
        orig = config.PUBLIC_HOSTNAME
        try:
            config.PUBLIC_HOSTNAME = "scholarly-mcp-production.up.railway.app"
            origins = config.allowed_origins()
            for o in ("https://claude.ai", "https://api.anthropic.com"):
                self.assertIn(o, origins, f"{o} would be refused 403")
            self.assertIn("https://scholarly-mcp-production.up.railway.app", origins)
        finally:
            config.PUBLIC_HOSTNAME = orig

    def test_arbitrary_origin_not_allowed(self):
        from app import config
        self.assertNotIn("https://attacker.example.com", config.allowed_origins())


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


class TestNewSourceHosts(unittest.TestCase):
    def test_new_hosts_allowlisted(self):
        for host in ("www.ebi.ac.uk", "inspirehep.net", "api.opencitations.net"):
            assert_allowed(f"https://{host}/x")

    def test_lookalikes_still_refused(self):
        for evil in ("https://inspirehep.net.attacker.com/x",
                     "https://api.opencitations.net.evil.io/x",
                     "https://evil.com/inspirehep.net"):
            with self.assertRaises(SecurityError, msg=f"allowed {evil}"):
                assert_allowed(evil)


class TestOpenCitationsIndependence(unittest.TestCase):
    """OpenCitations' index is built largely from reference lists deposited at
    Crossref, so agreement between the two is one deposit counted twice."""

    def test_opencitations_not_independent_of_crossref(self):
        self.assertEqual(merge.independent_count(["crossref", "opencitations"]), 1)

    def test_europepmc_is_independent(self):
        self.assertEqual(merge.independent_count(["crossref", "europepmc"]), 2)
        self.assertEqual(merge.independent_count(["openalex", "europepmc"]), 2)

    def test_inspire_is_independent(self):
        self.assertEqual(merge.independent_count(["openalex", "inspire"]), 2)


class TestOpenCitationsIdParsing(unittest.TestCase):
    def test_parses_packed_identifier_string(self):
        ids = sources._oc_ids(
            "omid:br/06120344846 doi:10.1038/nature12373 "
            "openalex:W2159974629 pmid:23903748")
        self.assertEqual(ids["doi"], "10.1038/nature12373")
        self.assertEqual(ids["openalex"], "W2159974629")
        self.assertEqual(ids["pmid"], "23903748")

    def test_handles_missing_and_empty(self):
        self.assertEqual(sources._oc_ids(""), {})
        self.assertEqual(sources._oc_ids(None), {})
        self.assertNotIn("doi", sources._oc_ids("omid:br/123"))


class TestEuropePmcRetractionSignal(unittest.TestCase):
    """MEDLINE curation is a retraction signal independent of Crossref deposits
    and of OpenAlex. Shapes copied from live Europe PMC responses."""

    def test_retracted_publication_type(self):
        rec = {"pub_types": ["Retracted Publication", "Journal Article"],
               "comment_corrections": []}
        status, notes = sources.epmc_publication_status(rec)
        self.assertEqual(status, "retracted")
        self.assertTrue(notes)

    def test_retraction_in_link(self):
        rec = {"pub_types": ["Journal Article"], "comment_corrections": [
            {"type": "Retraction in", "reference": "Lancet. 2010;375:445"}]}
        self.assertEqual(sources.epmc_publication_status(rec)[0], "retracted")

    def test_expression_of_concern(self):
        rec = {"pub_types": [], "comment_corrections": [
            {"type": "Expression of concern in", "reference": "x"}]}
        self.assertEqual(sources.epmc_publication_status(rec)[0], "concern")

    def test_comment_in_is_not_a_retraction(self):
        """"Comment in" is ordinary scholarly discussion, not a correction."""
        rec = {"pub_types": ["Journal Article"], "comment_corrections": [
            {"type": "Comment in", "reference": "Lancet. 1998;351:611"}]}
        self.assertEqual(sources.epmc_publication_status(rec)[0], "ok")

    def test_clean(self):
        self.assertEqual(sources.epmc_publication_status(
            {"pub_types": ["Journal Article"], "comment_corrections": []})[0], "ok")

    def test_type_skips_funding_categories(self):
        """MEDLINE sorts funding categories in with document types."""
        self.assertEqual(sources._epmc_type(
            ["Research Support, Non-U.S. Gov't", "research-article"]),
            "research-article")


class TestFullTextParsing(unittest.TestCase):
    """A JATS body commonly mixes bare <p> children with <sec> blocks. Taking
    only <sec> when any exists dropped 21 of 22 paragraphs on a real article."""

    def _parse(self, xml):
        import unittest.mock as mock
        with mock.patch.object(sources, "fetch", return_value=(xml.encode(), {})):
            return sources.europepmc_fulltext("PMC1")

    def test_mixed_loose_paragraphs_and_sections(self):
        ft = self._parse(
            "<article><front><abstract><p>Abs</p></abstract></front><body>"
            "<p>Loose one.</p><p>Loose two.</p>"
            "<sec><title>Methods</title><p>We did things.</p></sec>"
            "</body></article>")
        headings = [x["heading"] for x in ft["sections"]]
        self.assertEqual(headings, ["Abstract", "Body", "Methods"])
        body = next(x for x in ft["sections"] if x["heading"] == "Body")
        self.assertIn("Loose one.", body["text"])
        self.assertIn("Loose two.", body["text"])

    def test_sections_only(self):
        ft = self._parse("<article><body><sec><title>Results</title>"
                         "<p>Found it.</p></sec></body></article>")
        self.assertEqual([x["heading"] for x in ft["sections"]], ["Results"])

    def test_rejects_bad_pmcid(self):
        for bad in ("../../etc", "PMC", "12345", "PMC1; DROP", ""):
            with self.assertRaises(ValueError, msg=f"accepted {bad!r}"):
                sources.europepmc_fulltext(bad)


if __name__ == "__main__":
    unittest.main(verbosity=2)
