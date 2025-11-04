from __future__ import annotations

from types import SimpleNamespace

from medparse.validate.applicability import is_diagnostic_study


def _make_article(**kwargs):
    defaults = {
        "title": "Diagnostic yield of EBUS",
        "sections": {
            "abstract": "Diagnostic yield was assessed in a biopsy study",
            "introduction": "We evaluated diagnostic yield of bronchoscopy",
        },
        "tables": [],
        "yield_definitions_present": False,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_applicability_positive_signal():
    article = _make_article()
    applicable, reasons = is_diagnostic_study(article)
    assert applicable is True
    assert any(reason.startswith("primary_term") for reason in reasons)


def test_applicability_negative_signal():
    article = _make_article(
        title="Feasibility of Rheoplasty",
        sections={"abstract": "Feasibility and safety of rheoplasty treatment"},
    )
    applicable, reasons = is_diagnostic_study(article)
    assert applicable is False
    assert "negative_term:feasibility" in reasons or "missing_diagnostic_cues" in reasons
