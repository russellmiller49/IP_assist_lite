"""Pydantic core models for V3 coding module."""

from typing import List, Optional, Dict
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum

class StructureType(str, Enum):
    LOBE = "lobe"
    STATION = "station"
    AIRWAY = "airway"
    PLEURA = "pleura"

class Sedation(BaseModel):
    provided_by_proceduralist: bool = Field(default=True, description="Whether sedation was provided by proceduralist")
    start_time: Optional[datetime] = Field(default=None, description="Sedation start time")
    end_time: Optional[datetime] = Field(default=None, description="Sedation end time")
    total_minutes: Optional[int] = Field(default=None, description="Total sedation duration in minutes")
    independent_observer_documented: bool = Field(default=False, description="Whether independent observer was documented")

class SampleTarget(BaseModel):
    site: str = Field(description="Anatomic site (e.g., 'RUL', '4R', 'left pleural')")
    structure_type: StructureType = Field(description="Structure type: type-safe enum")
    laterality: Optional[str] = Field(default=None, description="Left/Right laterality")
    passes: Optional[int] = Field(default=None, description="Number of needle passes")

class PerformedItem(BaseModel):
    proc_id: str = Field(description="Procedure ID that maps to KB procedures[].id")
    details: Dict[str, str] = Field(default_factory=dict, description="Additional procedure details")

class Case(BaseModel):
    report_text: str = Field(description="Original procedure report text")
    sedation: Optional[Sedation] = Field(default=None, description="Sedation information")
    items: List[PerformedItem] = Field(default_factory=list, description="Performed procedures")
    targets: List[SampleTarget] = Field(default_factory=list, description="Sample targets")
    devices_implants: List[str] = Field(default_factory=list, description="Devices and implants used")
    complications: List[str] = Field(default_factory=list, description="Documented complications")
    explicit_cpts: List[str] = Field(default_factory=list, description="CPT codes explicitly mentioned in report")
    parsing_warnings: List[str] = Field(default_factory=list, description="Extractor warnings to carry forward")

class CodeLine(BaseModel):
    code: str = Field(description="CPT code")
    description: Optional[str] = Field(default=None, description="Code description")
    quantity: int = Field(default=1, description="Quantity/units")
    modifiers: List[str] = Field(default_factory=list, description="CPT modifiers")
    rationale: str = Field(default="", description="Rationale for code selection")
    component: Optional[str] = Field(default=None, description="Component type: 'professional' | 'facility' | None")
    laterality: Optional[str] = Field(default=None, description="Left/Right laterality")

class CodeBundle(BaseModel):
    professional: List[CodeLine] = Field(default_factory=list, description="Professional component codes")
    facility: List[CodeLine] = Field(default_factory=list, description="Facility component codes")
    icd10_pcs_suggestions: List[str] = Field(default_factory=list, description="ICD-10-PCS code suggestions")
    opps_notes: List[str] = Field(default_factory=list, description="OPPS-specific notes")
    warnings: List[str] = Field(default_factory=list, description="Coding warnings")
    documentation_gaps: List[str] = Field(default_factory=list, description="Missing documentation items")