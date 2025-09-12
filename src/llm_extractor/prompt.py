# SPDX-License-Identifier: MIT
SCHEMA_HINT = r"""
Return ONLY valid JSON matching this schema:

{
  "anesthesia": {"general": bool, "moderate": bool, "airway": "LMA|ETT|mask|unknown"},
  "procedures": [
    {"site": "trachea|bronchus|lobe|unknown",
     "action": "excision|destruction|dilation|stent_insertion|biopsy|ebus_tbna|radial_ebus|wll",
     "site_detail": "optional string (e.g., 'left main bronchus','RLL')",
     "details": {"method":"snare|APC|laser|balloon|forceps|needle|brush|...", "...": "..."},
     "specimens_collected": true|false|null,
     "count": integer|null}
  ],
  "stent": {"placed": bool, "location": "trachea|bronchus|both|unknown", "brand": "string|null", "size": "string|null"},
  "ebus": {"radial": bool, "stations_sampled": ["4R","7","4L","11R","..."]},
  "findings": {"obstruction_pct": int|null, "lesion_count": int|null},
  "explicit_negations": ["string", "..."],
  "evidence_spans": [{"field":"procedures[0]","text":"verbatim supporting snippet"}, ...]
}
"""

INSTRUCTIONS = r"""
You are a clinical NLP annotator. Convert the procedure note into the JSON schema.

Rules:
- If text says stent was only contemplated (e.g., "considered", "patient declined", "reluctant"), set stent.placed=false and add a negation such as "no stent placed".
- Mark excision when a snare/polypectomy transects/removes lesions and specimens are collected.
- If APC/laser/cryo used only for residual "painting"/"shaving" after snare, keep action=excision for that site (do not change to destruction).
- If ONLY APC/laser/cryo is used (no snare excision), use action=destruction.
- Whole lung lavage (WLL) → a procedure item with action="wll".
- Count distinct EBUS nodal stations (unique labels like 4R, 7, 4L).
- If GA/LMA/ETT present, set anesthesia.general=true and anesthesia.moderate=false.
- Use "site_detail" for precise location (e.g., "left main bronchus", "RLL").
- Do NOT infer codes. Return JSON only.

If uncertain about a field, set it to a sensible default (e.g., null, false, or "unknown") rather than hallucinating.
Return JSON only with no commentary.
"""

def build_prompt(note_text: str) -> str:
    return f"{SCHEMA_HINT}\n{INSTRUCTIONS}\n\nNOTE:\n{note_text}"