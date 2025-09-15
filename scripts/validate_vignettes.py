from __future__ import annotations
import json, re, sys
PATH = "datasets/ip_vignettes.jsonl"
def validate():
    cov = {"has_rb_segments":False,"has_gauge_sizes":False,"has_contraindications":False,"has_comparisons":False,"has_emergencies":False}
    with open(PATH) as f:
        for line in f:
            ex = json.loads(line); q = ex["question"].lower()
            if re.search(r'\b(?:rb|lb)[-\s]?\d+\b', q): cov["has_rb_segments"]=True
            if re.search(r'\d+\s*g(?:auge)?\b', q):   cov["has_gauge_sizes"]=True
            if re.search(r'\bcontraindicat', q):      cov["has_contraindications"]=True
            if re.search(r'\b(compare|versus|vs)\b', q): cov["has_comparisons"]=True
            if re.search(r'(massive hemoptysis|tension pneumo|emergency|urgent|stat)', q): cov["has_emergencies"]=True
    missing = [k for k,v in cov.items() if not v]
    if missing: print("Missing test coverage:", missing); sys.exit(1)
if __name__ == "__main__": validate()