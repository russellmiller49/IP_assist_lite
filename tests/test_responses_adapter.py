from src.adapters.openai_responses import Extraction


def test_extraction_model_schema_roundtrip():
    payload = {
        "primary_topic": "test",
        "secondary_topics": [],
        "evidence_items": [],
        "clinical_thresholds": [],
        "procedures": [],
        "diagnostic_criteria": [],
        "management_algorithms": [],
    }
    model = Extraction.model_validate(payload)
    dumped = model.model_dump()
    assert dumped["primary_topic"] == "test"
    assert dumped["clinical_thresholds"] == []
