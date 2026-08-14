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


class TestContextualizer:
    """FR-13, D-024: follow-ups must become standalone before retrieval."""

    def test_detects_dependent_followup(self):
        from app.chat.contextualizer import needs_rewrite
        hist = [{"role": "user", "content": "How is the AMF counter incremented?"}]
        assert needs_rewrite("What about for the SMF?", hist)
        assert needs_rewrite("Why?", hist)
        assert needs_rewrite("And the same for it?", hist)

    def test_standalone_question_untouched(self):
        from app.chat.contextualizer import needs_rewrite
        hist = [{"role": "user", "content": "earlier question"}]
        assert not needs_rewrite(
            "What HTTP status code is returned when a resource is replaced?", hist
        )

    def test_first_turn_never_rewritten(self):
        from app.chat.contextualizer import needs_rewrite
        assert not needs_rewrite("What about the SMF?", [])

    def test_no_llm_returns_original(self):
        from app.chat.contextualizer import contextualize
        q, changed = contextualize("Why?", [{"role": "user", "content": "x"}], llm=None)
        assert q == "Why?" and changed is False


class TestSessionGrounding:
    """D-025: history must not become a source of facts."""

    def test_history_holds_only_role_and_content(self):
        from app.chat.session import Session
        s = Session()
        s.add_user("q1")
        s.add_assistant({"answer": "a1", "citations": ["c1"], "confidence": 0.9})
        for turn in s.history():
            assert set(turn.keys()) == {"role", "content"}

    def test_turns_are_trimmed(self):
        from app.chat.session import Session, MAX_TURNS_KEPT
        s = Session()
        for i in range(MAX_TURNS_KEPT + 6):
            s.add_user(f"q{i}")
        assert len(s.turns) == MAX_TURNS_KEPT


class TestCitationNormalisation:
    """E-016: the validator must not be stricter than its own prompt format."""

    def test_bracketed_citation_accepted(self):
        from app.verification.citation_check import validate_citations
        r = validate_citations(["[TS28552_5.5.7.1.3]"], ["TS28552_5.5.7.1.3"])
        assert r.valid, r.reason

    def test_various_decorations_stripped(self):
        from app.verification.citation_check import normalise
        for raw in ["[abc_1]", "(abc_1)", "'abc_1'", '"abc_1"',
                    "  abc_1  ", "SOURCE: abc_1", "<abc_1>"]:
            assert normalise(raw) == "abc_1", raw

    def test_genuinely_fabricated_still_rejected(self):
        from app.verification.citation_check import validate_citations
        r = validate_citations(["[TS28552_9.9.9.9]"], ["TS28552_5.5.7.1.3"])
        assert not r.valid

    def test_chunk_map_resolves_decorated_id(self):
        from app.verification.citation_check import cited_chunk_map
        m = cited_chunk_map([{"chunk_id": "TS_1.2", "body": "x"}])
        from app.verification.citation_check import normalise
        assert m[normalise("[TS_1.2]")]["body"] == "x"
