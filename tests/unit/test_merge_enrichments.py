from __future__ import annotations

from src.normalize.merge_enrichments import extract_to_graph_payload


def test_extract_to_graph_payload_merges_enrichments() -> None:
    extract_resp = {
        "metadata": {"doc_id": "doc-1", "title": "Sample Doc"},
        "sections": [
            {
                "id": "s1",
                "title": "Introduction",
                "text": "Sample section.",
                "spans": [{"id": "span-1", "page": 1, "bbox": [0.1, 0.1, 0.9, 0.3]}],
            },
            {
                "id": "s2",
                "title": "Results",
                "text": "Results section.",
                "spans": [{"id": "span-2", "page": 2}],
            },
        ],
        "recommendations": [
            {
                "id": "rec-1",
                "text": "Consider bronchial thermoplasty.",
                "grade": "A",
                "spans": [{"id": "rec-span", "page": 1}],
            }
        ],
        "statistics": [
            {
                "id": "stat-1",
                "type": "sensitivity",
                "value": "0.92",
                "ci": "0.85-0.97",
                "spans": [{"id": "stat-span", "page": 2, "bbox": [0.2, 0.3, 0.8, 0.6]}],
            }
        ],
        "relations": [
            {"type": "SUPPORTED_BY", "source": "rec-1", "target": "stat-1"},
        ],
        "figures": [
            {"id": "fig-1", "caption": "Figure caption", "page": 2, "image_b64": None},
        ],
        "tables": [
            {"id": "tab-1", "caption": "Table caption", "page": 1},
        ],
        "quality": {"warnings": []},
        "validation": {"score": 0.9},
    }

    payload = extract_to_graph_payload(extract_resp)

    assert payload["doc_id"] == "doc-1"
    assert payload["doc_meta"]["title"] == "Sample Doc"

    recommendations = payload["nodes"]["Recommendation"]
    stats = payload["nodes"]["Stat"]
    figures = payload["nodes"]["Figure"]
    tables = payload["nodes"]["Table"]

    assert recommendations and stats and figures and tables

    rec_node = recommendations[0]
    assert rec_node["uid"].startswith("doc-1:rec:")
    assert rec_node["section_uid"].startswith("doc-1:section:")
    assert rec_node["span_id"] == "rec-span"

    stat_node = stats[0]
    assert stat_node["uid"].startswith("doc-1:stat:")
    assert stat_node["section_uid"].startswith("doc-1:section:")
    assert stat_node["bbox"] == [0.2, 0.3, 0.8, 0.6]
    assert stat_node["value"] == 0.92
    assert stat_node["ci"] == "0.85-0.97"

    figure_node = figures[0]
    assert figure_node["uid"].startswith("doc-1:fig:")
    assert figure_node["section_uid"].startswith("doc-1:section:")

    table_node = tables[0]
    assert table_node["uid"].startswith("doc-1:table:")
    assert table_node["section_uid"].startswith("doc-1:section:")

    edges = payload["edges"]
    assert edges[0]["type"] == "SUPPORTED_BY"
    assert edges[0]["source_uid"] == rec_node["uid"]
    assert edges[0]["target_uid"] == stat_node["uid"]
