from __future__ import annotations
import json, os, sys
from ragas.metrics import faithfulness, answer_relevancy, context_recall
from src.eval.numeric_accuracy import numeric_ok
from src.graph.flow import compiled_graph

DATASET = "datasets/ip_vignettes.jsonl"

def run_pipeline(question: str):
    out = compiled_graph.invoke({"query": question, "config": {}})
    answer = " ".join(out.get("answer_sentences", []))
    ctx = [c.get("text","") for c in out.get("retrieved_chunks",[])]
    return {"answer": answer, "contexts": ctx}

def evaluate():
    gold = [json.loads(l) for l in open(DATASET)]
    preds = []
    for ex in gold:
        out = run_pipeline(ex["question"])
        preds.append({"question": ex["question"], "answer": out["answer"],
                      "contexts": out["contexts"], "reference_contexts": ex["gold_contexts"],
                      "reference": ex["gold_answer"]})
    f  = faithfulness(preds); ar = answer_relevancy(preds); cr = context_recall(preds)
    num_ok = all(numeric_ok(p["answer"], p["reference"],
                            tol_pct=float(os.getenv("NUM_TOL","5.0")),
                            allow_gauge_off_by_one=os.getenv("ALLOW_GAUGE_OFF_BY_ONE","true").lower()=="true")
                 for p in preds)
    print(f"faithfulness={f:.3f} answer_relevancy={ar:.3f} context_recall={cr:.3f} numeric_ok={num_ok}")
    th = {"f": float(os.getenv("TH_F","0.75")), "ar": float(os.getenv("TH_AR","0.70")), "cr": float(os.getenv("TH_CR","0.70"))}
    if f < th["f"] or ar < th["ar"] or cr < th["cr"] or not num_ok: sys.exit(1)

if __name__ == "__main__": evaluate()