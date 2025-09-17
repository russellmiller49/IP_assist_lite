"""Knowledge base utilities: scan markdown/txt content and produce a structured report."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List

KB_DIR = Path("data/knowledge_base")
OUT_DIR = Path("data/structured_knowledge")
REPORT_PATH = Path("data/kb_analysis_report.json")

KB_DIR.mkdir(parents=True, exist_ok=True)
OUT_DIR.mkdir(parents=True, exist_ok=True)

PROC_PATTERNS: List[str] = [
    r"bronchoscopy",
    r"ebus",
    r"thoracentesis",
    r"chest tube",
    r"pleurodesis",
    r"navigation",
    r"cryotherapy",
    r"biopsy",
]
DIS_PATTERNS: List[str] = [
    r"nodule",
    r"mass",
    r"cancer",
    r"effusion",
    r"empyema",
    r"pneumothorax",
    r"hemoptysis",
    r"obstruction",
    r"stenosis",
    r"mesothelioma",
    r"ild",
    r"copd",
    r"asthma",
]
PMID_RE = re.compile(r"\bPMID[:\s]*([0-9]{7,8})\b", re.IGNORECASE)
DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b", re.IGNORECASE)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def scan() -> Dict[str, object]:
    """Walk the knowledge base directory and emit metadata plus lightweight stats."""
    report: Dict[str, object] = {
        "timestamp": datetime.now().isoformat(),
        "files": [],
        "stats": {"total": 0, "pmids": 0, "dois": 0},
    }

    for path in sorted(KB_DIR.rglob("*")):
        if path.is_dir() or path.suffix.lower() not in {".md", ".txt"}:
            continue
        text = _read_text(path)
        digest = hashlib.md5(text.encode("utf-8", errors="ignore")).hexdigest()
        procedures = [pat for pat in PROC_PATTERNS if re.search(pat, text, re.IGNORECASE)]
        diseases = [pat for pat in DIS_PATTERNS if re.search(pat, text, re.IGNORECASE)]
        pmids = PMID_RE.findall(text)
        dois = DOI_RE.findall(text)
        report["files"].append(
            {
                "path": str(path.relative_to(KB_DIR)),
                "md5": digest,
                "procedures": procedures,
                "diseases": diseases,
                "pmids": pmids,
                "dois": dois,
            }
        )
        report["stats"]["total"] += 1
        report["stats"]["pmids"] += len(pmids)
        report["stats"]["dois"] += len(dois)

    REPORT_PATH.write_text(json.dumps(report, indent=2))
    print(f"analysis complete -> {REPORT_PATH}")
    return report


if __name__ == "__main__":
    scan()
