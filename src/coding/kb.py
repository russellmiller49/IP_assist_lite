"""KB loader with enhanced features: fallback, descriptions, versioning."""

import json
from pathlib import Path
from typing import Any, Dict, Iterable, Optional
from datetime import datetime

class CodingKB:
    """
    Loads KB from preferred path or falls back automatically.
    Also exposes: code descriptions, bilateral eligible codes, and a version string.
    """
    DEFAULT_PATHS = [
        "data/ip_coding_billing.json",
        "data/coding_module.json"
    ]

    def __init__(self, path: Optional[str] = None):
        if path is None:
            # Try preferred first, then fallback
            chosen = None
            for p in self.DEFAULT_PATHS:
                if Path(p).exists():
                    chosen = p
                    break
            path = chosen or self.DEFAULT_PATHS[0]
        self.path = Path(path)
        self.data: Dict[str, Any] = self._load_json(self.path)
        if "procedures" not in self.data and self.path.name == "coding_module.json":
            # Back-compat normalization
            self.data = {
                "procedures": self.data.get("procedures", []),
                "global_principles": self.data.get("global_principles", {}),
                "compliance_and_edits": self.data.get("compliance_and_edits", {}),
            }
        # Build code-description map (from KB + our defaults)
        self._code_desc: Dict[str, str] = {}
        for p in self.data.get("procedures", []):
            name = p.get("name", "")
            for c in (p.get("cpt", []) or []) + (p.get("hcpcs", []) or []):
                self._code_desc.setdefault(c, name)
        # Helpful defaults (you can extend in the KB JSON later)
        self._code_desc.update({
            "31652": "Bronchoscopy with EBUS guided TBNA, 1–2 stations",
            "31653": "Bronchoscopy with EBUS guided TBNA, ≥3 stations",
            "+31654": "Bronchoscopy with diagnostic/radial EBUS (add‑on)",
            "+31627": "Computer-assisted navigation bronchoscopy (add‑on)",
            "31628": "Transbronchial lung biopsy, single lobe",
            "+31632": "Transbronchial lung biopsy, each additional lobe (add‑on)",
            "32554": "Thoracentesis, without imaging guidance",
            "32555": "Thoracentesis, with imaging guidance",
            "32556": "Pleural drainage catheter, without imaging",
            "32557": "Pleural drainage catheter, with imaging",
            "32550": "Insertion of tunneled indwelling pleural catheter",
            "99152": "Moderate sedation services by same physician, initial 15 min",
            "99153": "Moderate sedation, each additional 15 min (same physician)",
            "99155": "Moderate sedation, initial 15 min by different provider",
            "99156": "Moderate sedation, each additional 15 min (diff provider)",
            "99157": "Moderate sedation, each additional 15 min (diff provider, subsequent)",
            "31634": "Balloon occlusion/Collateral ventilation assessment (Chartis)",
            "31647": "Placement of endobronchial valve(s), initial lobe",
            "31641": "Bronchoscopic tumor destruction",
            "31622": "Diagnostic bronchoscopy",
        })

    @staticmethod
    def _load_json(path: Path) -> Dict[str, Any]:
        if not path.exists():
            alt = path.parent / "coding_module.json"
            if alt.exists():
                path = alt
            else:
                # Return minimal structure if nothing exists
                return {
                    "procedures": [],
                    "global_principles": {},
                    "compliance_and_edits": {}
                }
        return json.loads(path.read_text(encoding="utf-8"))

    def iter_procs(self) -> Iterable[Dict[str, Any]]:
        yield from self.data.get("procedures", [])

    def find_proc(self, proc_id: str) -> Dict[str, Any]:
        for p in self.iter_procs():
            if p.get("id") == proc_id:
                return p
        raise KeyError(proc_id)

    @property
    def gp(self) -> Dict[str, Any]:
        return self.data.get("global_principles", {})

    @property
    def compliance(self) -> Dict[str, Any]:
        return self.data.get("compliance_and_edits", {})

    # ------ Enhancements ------
    def describe(self, code: str) -> str:
        """Return a friendly description for CPT/HCPCS codes."""
        return self._code_desc.get(code, "")

    def bilateral_eligible_codes(self) -> Iterable[str]:
        """Return which codes can take -50; override in KB global_principles if desired."""
        from_gp = self.gp.get("bilateral_eligible_codes")
        if isinstance(from_gp, list):
            return from_gp
        # Conservative defaults—primarily pleural procedures
        return ["32554", "32555", "32556", "32557", "32550"]

    def version_info(self) -> str:
        """Human-readable KB version (metadata.version or file mtime)."""
        meta = self.data.get("metadata", {})
        if meta.get("version"):
            return f"{meta['version']}"
        try:
            ts = datetime.fromtimestamp(self.path.stat().st_mtime).isoformat(timespec="seconds")
            return f"file:{self.path.name} mtime:{ts}"
        except Exception:
            return f"file:{self.path.name}"