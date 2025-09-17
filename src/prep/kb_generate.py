"""Generate disease markdown files from structured extraction output."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import yaml

IN_JSON = Path("data/structured_knowledge/extractions.json")
OUT_DIR = Path("data/structured_knowledge/diseases")
OUT_DIR.mkdir(parents=True, exist_ok=True)

ABBREVIATIONS: Dict[str, List[str]] = {
    "lung_nodule": ["CT", "PET", "EBUS", "TTNA", "VDT"],
    "pleural_effusion": ["MPE", "IPC", "LDH", "pH"],
    "hemoptysis": ["BAE", "CTA", "FFB"],
}

DISPLAY_NAMES = {
    "lung_nodule": "Lung Nodule or Mass Evaluation",
    "pleural_effusion": "Pleural Effusion Management",
    "hemoptysis": "Hemoptysis Evaluation and Management",
}


def _front_matter(entity_type: str, files: List[str]) -> str:
    today = datetime.now().date().isoformat()
    front = {
        "schema_version": "1.1",
        "entity": entity_type,
        "last_reviewed": today,
        "evidence_cutoff": today,
        "source_files": files,
        "quality": {"groundedness": None, "completeness_score": None},
    }
    return "---\n" + yaml.safe_dump(front, sort_keys=False) + "---\n"


def _abbr_section(key: str) -> str:
    values = ABBREVIATIONS.get(key, [])
    if not values:
        return "None"
    return " ".join(f"{abbr} - [definition]" for abbr in values)


def _build_markdown(disease_key: str, entries: List[Dict[str, object]]) -> str:
    display_name = DISPLAY_NAMES.get(disease_key, disease_key.replace("_", " ").title())
    files = [entry.get("file", "") for entry in entries]
    header = _front_matter("disease", [str(f) for f in files])
    abbreviations = _abbr_section(disease_key)
    generated_date = datetime.now().date().isoformat()

    body_lines = [
        header,
        f"# {display_name} - Evidence-Based Knowledge File",
        f"*Generated: {generated_date} | Status: Auto-generated, Pending Review*",
        "",
        "## Abbreviations",
        abbreviations,
        "",
        "## Overview and Epidemiology",
        "[TBD]",
        "",
        "## Risk Stratification",
        "[TBD]",
        "",
        "## Diagnostic Approach",
        "[TBD]",
        "",
        "## Management Algorithm",
        "[TBD]",
        "",
        "## Procedures",
        "[TBD]",
        "",
        "## Evidence Tables",
        "[TBD]",
        "",
        "## Clinical Thresholds",
        "| Parameter | Threshold | Action | Evidence |",
        "|---|---|---|---|",
    ]

    for entry in entries:
        extraction = entry.get("extraction", {})
        if not isinstance(extraction, dict):
            continue
        for threshold in extraction.get("clinical_thresholds", []) or []:
            if not isinstance(threshold, dict):
                continue
            body_lines.append(
                "| {parameter} | {threshold} | {action} | {evidence} |".format(
                    parameter=threshold.get("parameter", ""),
                    threshold=threshold.get("threshold", ""),
                    action=threshold.get("action", ""),
                    evidence=threshold.get("evidence_basis", "extracted"),
                )
            )

    body_lines.extend([
        "",
        "## References",
        "References to be added.",
        "",
    ])

    return "\n".join(body_lines)


def run() -> Dict[str, List[Dict[str, object]]]:
    if not IN_JSON.exists():
        print(f"no structured extractions found -> {IN_JSON}")
        return {}

    entries = json.loads(IN_JSON.read_text())
    grouped: Dict[str, List[Dict[str, object]]] = {
        "lung_nodule": [],
        "pleural_effusion": [],
        "hemoptysis": [],
    }

    for entry in entries:
        entry_blob = json.dumps(entry).lower()
        for key in list(grouped.keys()):
            keywords = key.split("_")
            if any(word in entry_blob for word in keywords):
                grouped[key].append(entry)

    for key, docs in grouped.items():
        if not docs:
            continue
        out_path = OUT_DIR / f"{key}_knowledge.md"
        out_path.write_text(_build_markdown(key, docs))
        print(f"wrote {out_path}")

    return grouped


if __name__ == "__main__":
    run()
