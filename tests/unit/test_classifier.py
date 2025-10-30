from pathlib import Path

import pytest

from medparse.classify.model import classify_with_model
from medparse.classify.rules import classify_with_rules

pytestmark = pytest.mark.legacy_goldens

DATA_DIR = Path("tests/data/pdfs")
PDFS = {
    "ifu": DATA_DIR
    / "Ion Endoluminal System, Instruments, and Accessories User Manual(553990-11).pdf",
    "esge_guideline": DATA_DIR
    / "Combined EBUS  EUS for the diagnosis and staging of lung cancer ESGE, ERS, ESTS Guideline.pdf",
    "ats_guideline": DATA_DIR / "Guideline ATS diagnostic yield.pdf",
    "research": DATA_DIR / "Robotic Cyrobiopsy 2022.pdf",
    "book": DATA_DIR / "Treatment of Airway-Esophageal Fistulas.pdf",
}


def test_classifier_identifies_ifu() -> None:
    assert classify_with_rules(PDFS["ifu"]) == "ifu"


def test_classifier_identifies_guideline() -> None:
    assert classify_with_rules(PDFS["esge_guideline"]) == "guideline"


def test_classifier_identifies_research() -> None:
    assert classify_with_rules(PDFS["research"]) == "research"


def test_classifier_identifies_book_chapter() -> None:
    assert classify_with_rules(PDFS["book"]) == "book_chapter"


def test_classifier_handles_additional_guideline() -> None:
    assert classify_with_rules(PDFS["ats_guideline"]) == "guideline"


def test_model_classifier_falls_back_to_rules() -> None:
    assert classify_with_model(PDFS["ifu"]) == "ifu"
