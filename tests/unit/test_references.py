from medparse.normalize.references import gate_ifu_references


def test_gate_ifu_references_drops_non_bibliographic_entries() -> None:
    payload = {
        "references": [
            "Customer Service: 1-800-123-4567",
            "Table 6.2 Input Connections",
        ]
    }
    pages_text = [
        "Table 6.2 Input Connections\nIEC 60601-1-2",
        "For assistance call 1-800-123-4567",
    ]

    gate_ifu_references(payload, pages_text)
    assert payload["references"] == []
