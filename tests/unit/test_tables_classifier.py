from medparse.normalize.tables_classifier import classify_and_gate_tables


def test_paragraph_like_table_rejected():
    table = {
        "headers": ["n", "%"],
        "rows": [["1", " ".join(["word"] * 150)]]
    }
    assert classify_and_gate_tables([table]) == []


def test_cell_length_limit_applied():
    table = {
        "headers": ["n", "%"],
        "rows": [["1", "a" * 650]]
    }
    assert classify_and_gate_tables([table]) == []


def test_valid_medical_table_passes():
    table = {
        "title": "Table 1",
        "headers": ["n", "%"],
        "rows": [["10", "25"]]
    }
    result = classify_and_gate_tables([table])
    assert len(result) == 1
    assert result[0].table_type in {"diagnostic_accuracy", "baseline_characteristics", "other"}
