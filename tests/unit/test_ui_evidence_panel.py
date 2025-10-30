from __future__ import annotations

from src.ui import enhanced_gradio_app as ui


def test_format_response_renders_evidence_panel(monkeypatch):
    monkeypatch.setattr(ui, "APP_SHOW_EVIDENCE", True)

    result = {
        "query": "sample query",
        "response": "Sample answer.",
        "query_type": "clinical",
        "confidence_score": 0.8,
        "model_used": "gpt-5-mini",
        "evidence_summary": {"recommendations": 1, "stats": 2, "figures": 0, "tables": 1},
        "evidence_items": [
            {
                "recommendation": {
                    "text": "Consider bronchial thermoplasty",
                    "grade": "A",
                    "page": 3,
                    "supported_by": 2,
                },
                "statistics": [
                    {"stat_type": "sensitivity", "value": 0.92},
                    {"stat_type": "specificity", "value": 0.81},
                ],
                "figures": [],
                "tables": [
                    {"caption": "Outcome summary", "page": 4},
                ],
            }
        ],
    }

    html = ui.format_response_html(result, include_query=True)

    assert "Evidence Panel" in html
    assert "Supported by 2 stats" in html
    assert "sensitivity" in html
    assert "Outcome summary" in html
