from medparse.normalize.tables import clean_tables


def test_clean_tables_merges_continuations_and_dedupes() -> None:
    tables = [
        {
            "title": "Table 4.2 LED status indicators",
            "headers": ["State", "LED", "Action"],
            "rows": [["Ready", "Green", "Proceed"]],
            "page": 10,
        },
        {
            "title": "Table 4.2 LED status indicators (continued)",
            "headers": ["State", "LED", "Action"],
            "rows": [["Fault", "Red", "Halt"]],
            "page": 11,
        },
        {
            "title": None,
            "headers": [],
            "rows": [],
            "page": 12,
        },
        {
            "title": "Table 4.2 LED status indicators",
            "headers": ["State", "LED", "Action"],
            "rows": [["Ready", "Green", "Proceed"]],
            "page": 10,
        },
    ]

    cleaned = clean_tables(tables)
    assert len(cleaned) == 1
    assert cleaned[0]["rows"] == [["Ready", "Green", "Proceed"], ["Fault", "Red", "Halt"]]
