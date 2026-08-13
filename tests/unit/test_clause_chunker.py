"""Unit tests for the clause chunker (traceability: FR-03, DEF-03, E-001, E-002)."""

import pytest
from app.ingestion.clause_chunker import (
    chunk_spec, _looks_like_title, _is_plausible_successor, summarise,
)


def page(n, text):
    return {"page_number": n, "text": text}


class TestTitleDetection:
    """E-001: camelCase attribute names are valid 3GPP clause titles."""

    @pytest.mark.parametrize("title", [
        "perceivedSeverity", "alarmType", "gNBId", "Alarm clearing procedure",
        "Performance measurements",
    ])
    def test_accepts_valid_titles(self, title):
        assert _looks_like_title(title)

    @pytest.mark.parametrize("title", [
        "is defined in TS 23.501 and applies to all network functions here.",
        "shows the reference model for the system architecture in detail now.",
    ])
    def test_rejects_prose(self, title):
        assert not _looks_like_title(title)


class TestHierarchy:
    @pytest.mark.parametrize("prev,cur", [
        ("5", "5.1"), ("5.1", "5.2"), ("5.2.3", "5.3"), ("5.2.3", "6"),
    ])
    def test_plausible(self, prev, cur):
        assert _is_plausible_successor(prev, cur)

    @pytest.mark.parametrize("prev,cur", [
        ("7.4.1", "3.2"),      # figure caption "3.2 shows..."
        ("5.2.3", "5.2"),      # running header repeat
    ])
    def test_implausible(self, prev, cur):
        assert not _is_plausible_successor(prev, cur)


class TestChunking:
    def test_clause_spans_page_break(self):
        """DEF-03: the fork base chunked per page, splitting clauses."""
        chunks = chunk_spec([
            page(1, "5\tMeasurements\n5.1\tAMF counter\nThe AMF shall increment"),
            page(2, "the counter on each request received over the interface."),
        ], "TS 28.552", "V18.5.0")
        c = [x for x in chunks if x.clause_id == "5.1"][0]
        assert c.page_start == 1 and c.page_end == 2
        assert "counter on each request" in c.body

    def test_breadcrumb_is_hierarchical(self):
        chunks = chunk_spec([page(1,
            "5\tPerformance measurements\n5.1\tNF measurements\n"
            "5.1.1\tAMF counter definition\n"
            "The AMF shall count all successful registration requests received."
        )], "TS 28.552", "V18.5.0")
        c = [x for x in chunks if x.clause_id == "5.1.1"][0]
        assert c.heading_path.startswith("5 Performance measurements > 5.1")
        assert c.text.startswith("[TS 28.552 V18.5.0]")

    def test_rejects_captions_and_list_items(self):
        chunks = chunk_spec([page(1,
            "5\tMeasurements\n5.1\tCounter\n"
            "Figure 5.1-1 shows the model.\nTable 5.1-1 lists the types.\n"
            "a) This measurement counts requests.\nb) CC\n"
            "The AMF shall increment the counter on reception of each request."
        )], "TS 28.552", "V18.5.0")
        assert {c.clause_id for c in chunks} == {"5.1"}

    def test_short_attribute_clause_retained(self):
        """E-002: a length threshold alone silently discarded real content."""
        chunks = chunk_spec([page(1,
            "6\tAlarms\n6.1\tperceivedSeverity\n"
            "Indicates the severity assigned by the notifying entity here.\n"
            "6.2\talarmType\nCategorises the alarm raised by the entity.\n"
        )], "TS 28.532", "V18.5.0")
        assert "6.2" in {c.clause_id for c in chunks}

    def test_parent_container_skipped(self):
        chunks = chunk_spec([page(1,
            "5\tMeasurements\n5.1\tAMF\n"
            "The AMF shall count all registration requests received here now."
        )], "TS 28.552", "V18.5.0")
        assert "5" not in {c.clause_id for c in chunks}

    def test_oversized_clause_sub_split_with_overlap(self):
        body = "The AMF shall perform the procedure. " * 260
        chunks = chunk_spec([page(1, f"5\tBig\n5.1\tHuge\n{body}")],
                            "TS 23.501", "V18.4.0")
        assert len(chunks) > 1
        assert all(c.part_total == len(chunks) for c in chunks)
        assert all(c.clause_id == "5.1" for c in chunks)
        assert all(c.token_estimate <= 500 for c in chunks)

    def test_metadata_complete(self):
        """FR-03: 100% of chunks must populate all provenance fields."""
        chunks = chunk_spec([page(1,
            "5\tMeasurements\n5.1\tCounter definition\n"
            "The AMF shall count all successful registration requests here."
        )], "TS 28.552", "V18.5.0")
        for c in chunks:
            assert c.spec_id and c.spec_version and c.clause_id
            assert c.heading_path and c.chunk_id
    def test_empty_input_raises(self):
        with pytest.raises(ValueError):
            chunk_spec([], "TS 1", "V1")


class TestPdfExtractionRealities:
    """E-003: PDF extraction collapses 3GPP's tabs to single spaces."""

    def test_single_space_before_camelcase_title(self):
        chunks = chunk_spec([page(1,
            "6 Alarm handling\n"
            "6.1 perceivedSeverity\n"
            "Indicates the severity assigned by the notifying entity to this alarm.\n"
            "6.2 alarmType\n"
            "Categorises the alarm raised by the notifying entity for the manager.\n"
        )], "TS 28.532", "V18.5.0")
        ids = {c.clause_id for c in chunks}
        assert "6.1" in ids and "6.2" in ids

    def test_single_space_still_rejects_prose(self):
        chunks = chunk_spec([page(1,
            "5 Measurements\n5.1 Counter\n"
            "The AMF shall count every registration request received here now.\n"
            "5.2 is defined in TS 23.501 and applies to all network functions.\n"
        )], "TS 28.552", "V18.5.0")
        assert "5.2" not in {c.clause_id for c in chunks}
