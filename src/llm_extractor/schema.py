# SPDX-License-Identifier: MIT
from __future__ import annotations
from typing import List, Literal, Optional, Dict, Any
from pydantic import BaseModel, Field, validator

Airway = Literal["trachea", "bronchus", "lobe", "unknown"]
Action = Literal[
    "excision",           # snare/polypectomy with specimens
    "destruction",        # APC/laser/cryo without excision
    "dilation",           # airway dilation w/o stent
    "stent_insertion",    # stent actually placed
    "biopsy",             # generic biopsy (forceps/needle/brush)
    "ebus_tbna",          # linear EBUS TBNA (nodal sampling)
    "radial_ebus",        # diagnostic/peripheral radial EBUS
    "wll"                 # whole lung lavage
]

class EvidenceSpan(BaseModel):
    field: str
    text: str

class Anesthesia(BaseModel):
    general: bool = False
    moderate: bool = False
    airway: Literal["LMA", "ETT", "mask", "unknown"] = "unknown"

class ProcedureItem(BaseModel):
    site: Airway
    action: Action
    site_detail: Optional[str] = None  # e.g., "left main bronchus", "RLL"
    details: Dict[str, Any] = Field(default_factory=dict)
    specimens_collected: Optional[bool] = None
    count: Optional[int] = None

class Stent(BaseModel):
    placed: bool = False
    location: Literal["trachea", "bronchus", "both", "unknown"] = "unknown"
    brand: Optional[str] = None
    size: Optional[str] = None

class EBUS(BaseModel):
    radial: bool = False
    stations_sampled: List[str] = Field(default_factory=list)

    @validator("stations_sampled", pre=True, each_item=True)
    def norm_station(cls, v: str) -> str:
        return v.strip().upper().replace(" ", "")

class Findings(BaseModel):
    obstruction_pct: Optional[int] = None
    lesion_count: Optional[int] = None

class ExtractedCase(BaseModel):
    anesthesia: Anesthesia
    procedures: List[ProcedureItem]
    stent: Stent
    ebus: EBUS
    findings: Findings
    explicit_negations: List[str] = Field(default_factory=list)
    evidence_spans: List[EvidenceSpan] = Field(default_factory=list)

    @property
    def ebus_station_count(self) -> int:
        # Unique stations only
        return len(set(self.ebus.stations_sampled))