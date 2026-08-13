"""Fusion and abstention gate tests (traceability: FR-04, FR-07, DEF-04, DEF-06)."""

from app.retrieval.fusion import reciprocal_rank_fusion
from app.retrieval.bm25_index import tokenize
from app.generation.confidence import should_answer, confidence_from_retrieval


class TestRRF:
    def test_agreed_document_ranks_first(self):
        fused = reciprocal_rank_fusion([
            [("a", 9.0), ("b", 1.0)],
            [("b", 50.0), ("a", 40.0)],
        ])
        assert fused[0][0] == "a"

    def test_ignores_score_magnitude(self):
        """RRF must use rank only - that is why it needs no normalisation."""
        f1 = reciprocal_rank_fusion([[("a", 1000.0), ("b", 0.001)]])
        f2 = reciprocal_rank_fusion([[("a", 0.2), ("b", 0.1)]])
        assert [x[0] for x in f1] == [x[0] for x in f2]


class TestTokenizer:
    def test_preserves_telecom_identifiers(self):
        """FR-04: a naive \\w+ tokenizer shreds exactly the tokens BM25 exists for."""
        toks = tokenize("See TS 28.552 for gNB-CU-UP and 5QI values")
        assert "28.552" in toks and "gnb-cu-up" in toks and "5qi" in toks

    def test_also_indexes_split_parts(self):
        toks = tokenize("gNB-CU-UP")
        assert "gnb" in toks and "cu" in toks and "up" in toks


class TestAbstentionGate:
    def test_below_tau_abstains(self):
        assert not should_answer(0.20, tau=0.35)

    def test_above_tau_answers(self):
        assert should_answer(0.50, tau=0.35)

    def test_no_chunks_is_zero_confidence(self):
        assert confidence_from_retrieval(0.9, 0) == 0.0

    def test_confidence_ignores_chunk_count(self):
        """DEF-06: the old formula rewarded retrieving MORE chunks, which is
        not evidence that any of them is correct."""
        assert confidence_from_retrieval(0.7, 1) == confidence_from_retrieval(0.7, 5)
