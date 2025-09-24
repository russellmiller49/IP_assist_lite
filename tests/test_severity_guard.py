from src.llm.verifier import verify_answer
def test_critical_claim_requires_high_confidence():
    sents  = ["Administer 50mg epinephrine now."]
    chunks = [{"id":"C1","text":"Standard dose is 5 mg epinephrine in this setting."}]
    res = verify_answer(sents, chunks, 0.70, 0.90)
    assert res["missing"], "Critical dosage claim must not pass with low/absent support"