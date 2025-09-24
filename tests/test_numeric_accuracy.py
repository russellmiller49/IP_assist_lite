from src.eval.numeric_accuracy import numeric_ok
def test_mm_vs_cm():
    assert numeric_ok("Lesion 10 mm", "Lesion 1 cm", 5.0)
def test_gauge_off_by_one():
    assert numeric_ok("Use 19G needle", "Use 18G needle", 5.0, allow_gauge_off_by_one=True)
def test_range_match():
    assert numeric_ok("Diameter 5-7 mm", "Diameter 6 mm", 5.0)