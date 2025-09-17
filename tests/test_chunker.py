from src.index.build_chunks import chunk_markdown


def test_table_stays_intact():
    md = "| A | B |\n|---|---|\n|1|2|\n"
    parts = chunk_markdown(md, max_chars=50, overlap=0)
    assert "|---|" in parts[0]
