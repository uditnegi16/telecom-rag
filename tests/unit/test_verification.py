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

    def test_history_holds_only_role_and_content(self, tmp_path):
        from pathlib import Path
        import app.chat.store as st
        st.DB_PATH = Path(tmp_path) / "t.db"
        st._conn = None
        cid = st.create_conversation("v1", "q1")
        st.add_turn(cid, "user", "q1")
        st.add_turn(cid, "assistant", "a1", citations=["c1"], confidence=0.9)
        # Only role and content reach the prompt. Citations, confidence and
        # abstain reasons are stored for audit but never fed back in.
        for turn in st.history_for_prompt(cid):
            assert set(turn.keys()) == {"role", "content"}

    def test_history_is_bounded(self, tmp_path):
        from pathlib import Path
        import app.chat.store as st
        st.DB_PATH = Path(tmp_path) / "t2.db"
        st._conn = None
        cid = st.create_conversation("v1", "q")
        for i in range(20):
            st.add_turn(cid, "user", f"q{i}")
        assert len(st.history_for_prompt(cid, max_turns=8)) == 8


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



class TestConfigMatchesMeasurements:
    """E-030: tau was reverted from its measured value to a guess by a patch
    that shipped the whole config file. The operating point is the single most
    consequential parameter in the system; it gets a test."""

    def test_tau_matches_measured_optimum(self):
        import json
        from pathlib import Path
        from app.config import CFG

        sweep = Path("eval/results/tau_sweep.json")
        if not sweep.exists():
            import pytest
            pytest.skip("no sweep recorded yet")

        best = json.loads(sweep.read_text(encoding="utf-8"))["best"]["tau"]
        assert abs(CFG.tau_abstain - best) < 1e-6, (
            f"CFG.tau_abstain={CFG.tau_abstain} but the measured optimum is "
            f"{best}. Either re-run scripts/sweep_tau.py or restore the value."
        )

    def test_generation_model_is_not_the_rate_limited_one(self):
        """D-027: llama-3.3-70b-versatile has a 1000 requests/DAY cap, which
        one day of development exhausts before a visitor ever clicks."""
        from app.config import CFG
        assert "70b" not in CFG.gen_model, (
            "70B model has a 1000/day request cap - unusable for a public demo"
        )
