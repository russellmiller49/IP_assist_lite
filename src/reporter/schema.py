from __future__ import annotations
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, validator

ROSEType = Literal["positive", "negative", "adequate", "atypical", "n/a", "not documented"]

class LesionSampling(BaseModel):
    modality: Literal["TBNA", "Cryobiopsy", "Forceps", "Brush", "BAL", "Other"]
    gauge_or_size: Optional[str] = None   # e.g., "23G" or "1.1 mm"
    passes: Optional[int] = None
    rose: ROSEType = "not documented"

class EBUSStationSample(BaseModel):
    station: str                         # e.g., "4R", "7", "11R"
    short_axis_mm: Optional[int] = None  # size if provided
    needle_gauge: Optional[str] = None   # e.g., "22G"
    passes: Optional[int] = None
    rose: ROSEType = "not documented"

class RoboticBronchoscopy(BaseModel):
    platform: Literal["Ion", "Monarch", "Other"] = "Ion"
    airway: Optional[Literal["ETT", "LMA", "Mask", "Nasal cannula"]] = None
    anesthesia: Optional[Literal["general", "moderate sedation", "MAC", "local"]] = None
    target_location: Optional[str] = None         # e.g., "RLL anterior segment"
    cbct_tool_in_lesion: bool = False
    lesion_samples: List[LesionSampling] = Field(default_factory=list)

class EBUSStaging(BaseModel):
    performed: bool = False
    samples: List[EBUSStationSample] = Field(default_factory=list)

class Complications(BaseModel):
    pneumothorax: Optional[Literal["no", "yes"]] = None
    bleeding: Optional[Literal["none", "minimal", "mild", "moderate", "severe"]] = None
    hypoxemia_intervention: Optional[Literal["no", "yes"]] = None
    other: Optional[str] = None

class ReporterParseResult(BaseModel):
    rb: RoboticBronchoscopy
    ebus: EBUSStaging
    complications: Complications
    rose_summary_lesion: ROSEType = "not documented"
    rose_summary_ebus: ROSEType = "not documented"
    data_warnings: List[str] = Field(default_factory=list)

    @validator("rose_summary_lesion", "rose_summary_ebus", pre=True, always=True)
    def normalize_rose(cls, v):
        return (v or "not documented").lower()