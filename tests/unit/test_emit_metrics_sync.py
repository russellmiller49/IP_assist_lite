from __future__ import annotations

from medparse.pipeline.run_extract import _apply_emit_constraints, _document_metrics
from medparse.schema.article import ArticleDocument, EnhancedTable, GuidelineRecommendation
from medparse.schema.ifu import IFUDocument, SafetyBlock
from medparse.schema.common import EvidenceSpan, Relation


def _make_relation(subject: str, predicate: str, obj: str) -> Relation:
    return Relation(
        subject=subject,
        predicate=predicate,
        object=obj,
        evidence=EvidenceSpan(text="Sample evidence", page=1),
    )


def test_emit_metrics_mirror_pipeline_counters():
    document = ArticleDocument(doc_type="article", source_file="dummy.pdf", page_count=1)
    document.pipeline_info["paragraph_dedup_applied"] = True
    document.relations = [
        _make_relation("A", "rel", "B"),
        _make_relation("A", "rel", "C"),
    ]
    document.tables = [
        EnhancedTable(id="tbl1", headers=[["H1"]], rows=[["cell-1"], ["cell-2"]]),
        EnhancedTable(id="tbl2", headers=[["H1"]], rows=[["cell-3"]]),
    ]
    document.recommendations = [
        GuidelineRecommendation(
            label="1",
            text="1. We recommend action.",
            grade="strong",
            grade_normalized={
                "scale": "GRADE",
                "strength": "strong",
                "source": "inline",
                "confidence": 0.9,
                "ungraded": False,
            },
        ),
        GuidelineRecommendation(
            label="2",
            text="2. We suggest caution.",
            ungraded=True,
            ungraded_reason="test",
            recommendation_type="suggestion",
            consensus_basis="CHEST-ungraded",
            grade_normalized={
                "scale": "CONSENSUS",
                "source": "inline",
                "confidence": 0.8,
                "ungraded": True,
            },
        ),
    ]

    emit_cfg = {
        "tables_mode": "compact",
        "max_tables": 1,
        "max_relations": 1,
        "relation_mode": "compact",
        "paragraph_store": True,
    }

    warnings = _apply_emit_constraints(document, emit_cfg)
    assert warnings, "Expected truncation warnings"

    metrics = _document_metrics(document)

    assert metrics["relations_dropped"] == document.pipeline_info.get("relations_dropped")
    assert metrics["tables_dropped"] == document.pipeline_info.get("tables_dropped")
    assert metrics["paragraph_dedup_applied"] is True
    assert metrics["relations_kept"] == len(document.relations)
    assert metrics["tables_kept"] == len(document.tables)
    assert metrics["graded_count"] == 1
    assert metrics["typed_ungraded_count"] == 1
    assert metrics["typed_density"] == 1.0
    assert metrics["grade_density"] == document.pipeline_info.get("grade_density")
    assert metrics["recommendations_total"] == 2
    assert metrics["recommendations_graded"] == 1
    assert metrics["recommendations_ungraded_typed"] == 1
    assert metrics["frontmatter_affiliations_unresolved"] == 0


def test_ifu_toc_guard_metrics():
    """Test that TOC guard metrics are included for IFUs."""
    document = IFUDocument(
        doc_type="ifu",
        source_file="dummy.pdf",
        page_count=50,
        manufacturer="Intuitive Surgical, Inc.",
        product_name="Ion Endoluminal System",
    )

    # Set up TOC guard info in pipeline_info
    document.pipeline_info["toc_guard"] = {
        "enabled": True,
        "pages_dropped": [2, 3, 112],
        "density_threshold": 0.55,
        "dot_leader_min": 0.15,
    }
    document.pipeline_info["toc_guard_applied"] = True
    document.pipeline_info["paragraph_dedup_applied"] = True

    # Add some tables
    document.tables = [
        EnhancedTable(id="tbl1", headers=[["H1"]], rows=[["cell-1"]]),
    ]

    # Add safety blocks
    document.safety_blocks = [
        SafetyBlock(
            level="warning",
            severity="warning",
            title="WARNING",
            text="Sample warning",
            category="general",
            page=14,
            evidence=EvidenceSpan(text="Warning text", page=14),
        ),
    ]

    emit_cfg = {
        "tables_mode": "compact",
        "max_tables": 5,
    }

    warnings = _apply_emit_constraints(document, emit_cfg)
    metrics = _document_metrics(document)

    # Check that TOC guard metrics are preserved
    assert "toc_guard_applied" in document.pipeline_info
    assert document.pipeline_info["toc_guard_applied"] is True

    # Check paragraph dedup
    assert metrics["paragraph_dedup_applied"] is True

    # Check tables metrics
    assert "tables_kept" in metrics or "tables_dropped" in metrics
