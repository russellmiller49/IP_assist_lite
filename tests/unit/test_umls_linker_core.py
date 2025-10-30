from medparse.linking.umls_linker import _overlap, _valid_span_for_linking, link_umls_spans


def test_overlap_excludes_touching_ranges() -> None:
    assert not _overlap((0, 5), (5, 10))
    assert _overlap((0, 5), (4, 10))


def test_valid_span_checks_whitelist_and_bounds() -> None:
    span = {"start": 0, "end": 5, "text": "term", "tui": "T123"}
    assert _valid_span_for_linking(span, ["T123"])
    assert not _valid_span_for_linking(span, ["T999"])
    assert not _valid_span_for_linking({"start": 5, "end": 5, "text": "x", "tui": "T123"}, ["T123"])


def test_link_umls_spans_filters_and_deduplicates() -> None:
    spans = [
        {"start": 0, "end": 5, "text": "alpha", "tui": "T123"},
        {"start": 4, "end": 9, "text": "beta", "tui": "T123"},
        {"start": 10, "end": 15, "text": "gamma", "tui": "T999"},
    ]
    linked = link_umls_spans(spans, ["T123"])
    assert linked == [{"start": 0, "end": 5, "text": "alpha", "tui": "T123"}]
