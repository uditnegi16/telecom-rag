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


class TestIntentClassification:
    """E-021: a greeting must never be rewritten into the previous question."""

    def test_greetings_not_billable(self):
        from app.chat.intent import Intent, classify
        for t in ["hi", "hello", "hey there!", "thanks", "ok", "bye",
                  "Hello, hello, hello.", "test test"]:
            c = classify(t, has_history=True)
            assert c.intent == Intent.GREETING, t
            assert not c.billable, t

    def test_meta_questions_answered_directly(self):
        from app.chat.intent import Intent, classify
        for t in ["what can you do?", "which specs do you know?", "who are you"]:
            assert classify(t, has_history=False).intent == Intent.META, t

    def test_real_followups_still_route_to_rag(self):
        from app.chat.intent import Intent, classify
        for t in ["what about for the AMF?", "why?", "and the SMF?"]:
            c = classify(t, has_history=True)
            assert c.intent == Intent.FOLLOW_UP, t
            assert c.billable, t

    def test_spec_questions_billable(self):
        from app.chat.intent import Intent, classify
        c = classify("How is the aggregated active session time measured?", True)
        assert c.intent == Intent.SPEC_QUESTION and c.billable

    def test_ambiguous_short_input_is_unclear_not_rewritten(self):
        from app.chat.intent import Intent, classify
        assert classify("5QI", has_history=True).intent == Intent.UNCLEAR

    def test_greeting_never_triggers_rewrite(self):
        from app.chat.contextualizer import needs_rewrite
        hist = [{"role": "user", "content": "What is the PCF counter unit?"}]
        assert not needs_rewrite("Hello, hello, hello.", hist)
        assert not needs_rewrite("hi", hist)
        assert needs_rewrite("what about for the AMF?", hist)


class TestRouteBindings:
    """E-022: every route must bind to its intended handler.

    A helper function inserted between a decorator and its function silently
    rebinds the route to the helper. FastAPI accepts it; the failure appears
    only at request time as a response-validation error.
    """

    def test_routes_bind_to_correct_handlers(self):
        from app.api.routes import router
        expected = {
            ("/chat", "POST"): "chat",
            ("/health", "GET"): "health",
            ("/corpus", "GET"): "corpus",
            ("/upload", "POST"): "upload",
            ("/quota", "GET"): "quota_status",
            ("/conversations", "GET"): "list_conversations",
        }
        actual = {
            (r.path, m): r.name
            for r in router.routes
            for m in r.methods
            if not m.startswith("HEAD")
        }
        for key, name in expected.items():
            assert actual.get(key) == name, f"{key} -> {actual.get(key)}, want {name}"


class TestRequestValidationMatchesClassifier:
    """E-023: the validator must not reject inputs the classifier handles."""

    def test_short_greetings_pass_validation(self):
        from app.api.routes import ChatRequest
        for q in ["hi", "ok", "hey", "5QI", "a"]:
            ChatRequest(question=q)          # must not raise

    def test_empty_still_rejected(self):
        import pydantic
        from app.api.routes import ChatRequest
        try:
            ChatRequest(question="")
            raise AssertionError("empty question should be rejected")
        except pydantic.ValidationError:
            pass

    def test_every_accepted_input_has_an_intent(self):
        from app.api.routes import ChatRequest
        from app.chat.intent import classify
        for q in ["hi", "5QI", "why?", "What is the PCF counter unit?"]:
            ChatRequest(question=q)
            assert classify(q, has_history=True).intent is not None


class TestSessionSystemConsistency:
    """E-026: upload and chat must scope documents with the SAME identifier."""

    def test_routes_use_one_session_system(self):
        """The in-memory SessionStore was superseded by the SQLite store.
        Any lingering import means two subsystems mint different ids for the
        same conversation, and session-scoped retrieval silently fails."""
        from pathlib import Path
        src = Path("app/api/routes.py").read_text(encoding="utf-8")
        assert "from app.chat.session import STORE" not in src, (
            "routes.py still imports the superseded in-memory session store"
        )
        assert "from app.chat import store" in src
