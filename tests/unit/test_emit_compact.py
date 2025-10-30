from medparse.schema.article import ArticleDocument, GuidelineRecommendation
from medparse.schema.common import EvidenceSpan, Relation, SizeGuards
from medparse.pipeline.run_extract import _apply_emit_constraints, _build_evidence_bank


def test_paragraph_store_and_refs():
    document = ArticleDocument(
        source_file="sample.pdf",
        page_count=3,
        title="Paragraph Store Test",
        sections={"introduction": "Paragraph one.\n\nParagraph two."},
        recommendations=[
            GuidelineRecommendation(
                label="R1",
                text="Rec 1",
                evidence=EvidenceSpan(text="Paragraph one."),
            ),
            GuidelineRecommendation(
                label="R2",
                text="Rec 2",
                evidence=EvidenceSpan(text="Paragraph two."),
            ),
        ],
    )

    _apply_emit_constraints(
        document,
        {"evidence_policy": "compact", "paragraph_store": True},
    )

    assert document.paragraph_store
    hashes = list(document.paragraph_store.keys())
    assert len(hashes) == 2
    for rec in document.recommendations:
        assert rec.evidence.text is None
        assert rec.evidence.paragraph_hash in hashes
        store_entry = document.paragraph_store[rec.evidence.paragraph_hash]
        assert isinstance(store_entry, dict)
        stored_text = store_entry.get("text")
        assert isinstance(stored_text, str)
        assert rec.evidence.paragraph_offset == (0, len(stored_text))
    assert "section_paragraph_refs" in document.pipeline_info


def test_relation_aggregation_caps():
    relations = [
        Relation(subject="A", predicate="rel", object="B", attributes={"page": 1}),
        Relation(subject="A", predicate="rel", object="B", attributes={"page": 1}),
        Relation(subject="A", predicate="rel", object="B", attributes={"page": 1}),
        Relation(subject="C", predicate="rel", object="D", attributes={"page": 2}),
    ]
    document = ArticleDocument(
        source_file="sample.pdf",
        page_count=3,
        title="Relations Test",
        relations=relations,
    )

    warnings = _apply_emit_constraints(
        document,
        {
            "relation_mode": "compact",
            "max_relations_per_pair": 2,
            "max_relations": 1,
        },
    )

    assert len(document.relations) == 1
    aggregated = document.relations[0]
    assert aggregated.attributes.get("count") == 3
    assert document.pipeline_info.get("relations_mode") == "compact"
    assert document.pipeline_info.get("relations_truncated") is True
    assert document.pipeline_info.get("relations_original") == 4
    assert document.pipeline_info.get("relations_kept") == 1
    assert document.pipeline_info.get("relations_dropped") == 1
    assert "relations_truncated" in warnings


def test_evidence_bank_uses_paragraph_store():
    document = ArticleDocument(
        source_file="sample.pdf",
        page_count=3,
        title="Evidence Bank Test",
        recommendations=[
            GuidelineRecommendation(
                label="R1",
                text="Rec 1",
                evidence=EvidenceSpan(text="Evidence paragraph one."),
            )
        ],
    )

    _apply_emit_constraints(
        document,
        {"evidence_policy": "compact", "paragraph_store": True},
    )

    rec = document.recommendations[0]
    assert rec.evidence.text is None
    bank = _build_evidence_bank(document, SizeGuards())
    evidence_payload = bank.get_bank()
    assert evidence_payload
    rec_pointer = document.recommendations[0].evidence
    assert rec_pointer.hash in evidence_payload
    paragraph_entry = document.paragraph_store.get(rec_pointer.paragraph_hash)
    assert paragraph_entry and isinstance(paragraph_entry, dict)
    assert paragraph_entry.get("text")
    ref_payload = evidence_payload[rec_pointer.hash]
    assert isinstance(ref_payload, dict)
    assert ref_payload.get("paragraph_hash") == rec_pointer.paragraph_hash
    assert "start" in ref_payload and "end" in ref_payload
    assert "text" not in ref_payload
