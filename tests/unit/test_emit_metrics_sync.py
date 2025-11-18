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
    document.pipeline_info["second_pass"] = {
        "applied": ["patch_a"],
        "patches_applied": ["patch_a"],
        "modifications": {"diagnostic_yield_numerator": 1},
        "diff_summary": {"diagnostic_yield_numerator": 1},
        "reasons": ["ats_diagnostic_yield_backfill"],
        "patch_summaries": [
            {
                "name": "patch_a",
                "modifications": {"diagnostic_yield_numerator": 1},
                "reasons": ["ats_diagnostic_yield_backfill"],
            }
        ],
    }
    document.ats_profile.is_diagnostic_study = False
    document.ats_profile.strict_yield_required = False
    document.ats_profile.strict_yield_observed = False
    document.ats_profile.strict_exclusion_reasons = ["not_diagnostic_study"]
    document.pipeline_info["safety_blocks_added"] = 2
    document.pipeline_info["safety_expected_min"] = 12
    document.pipeline_info["references_anchor_backfill"] = True
    document.pipeline_info["references_anchor"] = {"pages": [9, 10], "source": "second-pass:test"}
    document.pipeline_info["toc_guard_pages_dropped"] = [3, 4]
    document.pipeline_info["toc_guard_pages_dropped_count"] = 2
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

    assert metrics["research_scope"] == "unknown"
    assert metrics["imrad_required"] is False
    assert metrics["ats_yield_required"] is False
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
    assert metrics["second_pass_applied"] is True
    assert metrics["second_pass_patches"] == ["patch_a"]
    assert metrics["second_pass_reasons"] == ["ats_diagnostic_yield_backfill"]
    assert metrics["second_pass_modifications"] == {"diagnostic_yield_numerator": 1}
    assert metrics["ats_profile"]["is_diagnostic_study"] is False
    assert metrics["ats_profile"]["strict_exclusion_reasons"] == ["not_diagnostic_study"]
    assert "safety_blocks_added" not in metrics or isinstance(metrics["safety_blocks_added"], int)
    assert "safety_expected_min" not in metrics or isinstance(metrics["safety_expected_min"], int)

    assert "second_pass" in metrics
    sp_payload = metrics["second_pass"]
    assert sp_payload["applied"] == ["patch_a"]
    assert sp_payload["reasons"] == ["ats_diagnostic_yield_backfill"]
    assert sp_payload["modifications"] == {"diagnostic_yield_numerator": 1}

    summary = metrics.get("_metrics")
    assert isinstance(summary, dict)
    assert summary["second_pass_applied"] is True
    assert summary["second_pass_patches"] == ["patch_a"]
    assert summary["second_pass_reasons"] == ["ats_diagnostic_yield_backfill"]
    assert summary["second_pass_modifications"] == {"diagnostic_yield_numerator": 1}
    assert summary["tables_original"] == document.pipeline_info.get("tables_original")
    assert summary["tables_kept"] == metrics["tables_kept"]
    assert summary["tables_dropped"] == metrics["tables_dropped"]
    first_patch = summary["patches"][0]
    assert first_patch["name"] == "patch_a"
    assert first_patch["modifications"] == {"diagnostic_yield_numerator": 1}
    assert first_patch["reasons"] == ["ats_diagnostic_yield_backfill"]


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
    document.pipeline_info["toc_guard_pages_dropped"] = [2, 3, 50]
    document.pipeline_info["toc_guard_pages_dropped_count"] = 3
    document.pipeline_info["paragraph_dedup_applied"] = True
    second_pass_bucket = document.pipeline_info.setdefault("second_pass", {})
    modifications = second_pass_bucket.setdefault("modifications", {})
    modifications["sections_rebuilt"] = 3

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

    document.pipeline_info["safety_blocks_added"] = 2
    document.pipeline_info["safety_expected_min"] = 10
    document.pipeline_info["references_anchor_backfill"] = True
    document.pipeline_info["references_anchor"] = {"pages": [49, 50]}

    warnings = _apply_emit_constraints(document, emit_cfg)
    metrics = _document_metrics(document)

    # Check that TOC guard metrics are preserved
    assert "toc_guard_applied" in document.pipeline_info
    assert document.pipeline_info["toc_guard_applied"] is True

    # Check paragraph dedup
    assert metrics["paragraph_dedup_applied"] is True

    # Check tables metrics
    assert "tables_kept" in metrics or "tables_dropped" in metrics
    assert metrics["safety_blocks_found"] == len(document.safety_blocks)
    assert metrics["safety_blocks_added"] == 2
    assert metrics["safety_expected_min"] == 10
    assert metrics["references_anchor_backfill"] is True
    assert metrics["references_anchor_pages"] == [49, 50]
    assert metrics["toc_pages_dropped"][-1] == 50
    assert metrics["toc_drop_count"] == len(document.pipeline_info["toc_guard_pages_dropped"])
    summary = metrics.get("_metrics", {})
    assert summary.get("safety_expected_min") == 10
    assert summary.get("safety_found") == len(document.safety_blocks)
    assert summary.get("safety_gap") == max(0, 10 - len(document.safety_blocks))
    assert "safety_threshold_rule" in summary
    assert summary.get("sections_rebuilt") == 3
    assert summary.get("sectionizer_mode") == "ifu_salvage"
    assert summary.get("revision_status") == document.pipeline_info.get("revision_status")
