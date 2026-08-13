"""Verification tests (traceability: FR-06, FR-08, DEF-01, DEF-02)."""

from app.verification.citation_check import validate_citations
from app.verification.entailment import lexical_overlap, _parse_verdict


class TestCitationValidation:
    """DEF-01: an unresolvable citation must fail, never substitute."""

    def test_valid(self):
        r = validate_citations(["c1"], ["c1", "c2"])
        assert r.valid

    def test_fabricated_citation_fails(self):
        r = validate_citations(["TS28552_9.9.9"], ["c1"], known_ids={"c1"})
        assert not r.valid and r.fabricated == ["TS28552_9.9.9"]

    def test_real_but_not_retrieved_reported_separately(self):
        r = validate_citations(["c9"], ["c1"], known_ids={"c1", "c9"})
        assert not r.valid and r.out_of_context == ["c9"] and not r.fabricated

    def test_no_citation_fails(self):
        assert not validate_citations([], ["c1"]).valid


class TestEntailmentPrefilter:
    def test_low_overlap_detected(self):
        assert lexical_overlap(
            "The SMF handles quality of service flows",
            "Alarm severity indicates urgency assigned by notifying entity",
        ) < 0.10

    def test_negation_is_NOT_caught_by_overlap(self):
        """DEF-02: this is exactly why overlap cannot be the real check.
        The inverted claim scores as highly grounded."""
        source = "The AMF shall reject the registration request when invalid."
        claim = "The AMF shall not reject the registration request when invalid."
        # 0.89 - overwhelmingly "grounded" by any sane overlap threshold,
        # despite the claim asserting the exact opposite of the source.
        assert lexical_overlap(claim, source) > 0.85


class TestVerdictParsing:
    def test_parses_json(self):
        assert _parse_verdict('{"verdict":"SUPPORTED","reason":"x"}')["verdict"] == "SUPPORTED"

    def test_unparseable_fails_closed(self):
        """NFR-03: an unreadable verifier response must never become an accepted claim."""
        assert _parse_verdict("garbage")["verdict"] == "NOT_SUPPORTED"
