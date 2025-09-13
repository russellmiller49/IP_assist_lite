"""Pydantic models mirroring the strict JSON Schema v1 for IP procedure reports."""

from typing import List, Optional, Literal, Dict, Any
from datetime import date
from pydantic import BaseModel, Field, validator


class PatientInfo(BaseModel):
    """Patient demographic information."""
    name: str
    dod_id: str = Field(description="DoD ID")
    dob: str = Field(pattern=r'^\d{4}-\d{2}-\d{2}$')


class ProcedureContext(BaseModel):
    """Procedure context and setting."""
    date: str = Field(pattern=r'^\d{4}-\d{2}-\d{2}$')
    location: str
    elective_vs_emergency: Literal["elective", "emergency"]
    asa: Optional[Literal["I", "II", "III", "IV", "V"]] = None


class TopicalLidocaine(BaseModel):
    """Topical lidocaine dosing information."""
    ml: float = 0
    percent: float = 1.0
    mg: float = 0
    mg_per_kg: float = 0.0


class AnesthesiaInfo(BaseModel):
    """Anesthesia/sedation information."""
    method: Optional[Literal["GA", "Moderate", "Local"]] = None
    airway: Optional[Literal["ETT", "LMA", "None"]] = None
    provider: Optional[Literal["Anesthesiology", "Proceduralist", "RN"]] = None
    topical_lidocaine: Optional[TopicalLidocaine] = None


class Lesion(BaseModel):
    """Lesion description."""
    location: str
    size_mm: Optional[float] = None
    description: Optional[str] = None


class Findings(BaseModel):
    """Procedural findings."""
    airway: Optional[str] = None
    lesions: List[Lesion] = Field(default_factory=list)
    pleura: Optional[str] = None
    notes: Optional[str] = None


class Device(BaseModel):
    """Medical device used."""
    type: Literal["UC180F", "Q190", "Ion", "Monarch", "Cryoprobe", "EBUS_needle", "Other"]
    size_gauge_mm: Optional[str] = None
    details: Optional[str] = None


class FluoroGuidance(BaseModel):
    """Fluoroscopy guidance metrics."""
    used: bool = False
    time_min: Optional[float] = None
    air_kerma_mGy: Optional[float] = None
    dap_uGy_m2: Optional[float] = None


class CBCTGuidance(BaseModel):
    """Cone-beam CT guidance."""
    system: Optional[Literal["Cios_Spin", "Fixed_CBCT", "Mobile_CBCT"]] = None
    spins: Optional[int] = None
    contrast_ml: Optional[float] = None


class DigitalTomography(BaseModel):
    """Digital tomosynthesis."""
    used: bool = False


class RadialEBUS(BaseModel):
    """Radial EBUS findings."""
    used: bool = False
    view: Optional[Literal["concentric", "eccentric", "aerated"]] = None
    echogenicity: Optional[Literal["homogeneous", "heterogeneous"]] = None
    air_bronchogram: Optional[bool] = None


class ImagingGuidance(BaseModel):
    """All imaging guidance modalities."""
    fluoro: Optional[FluoroGuidance] = None
    cbct: Optional[CBCTGuidance] = None
    digital_tomography: Optional[DigitalTomography] = None
    rebus: Optional[RadialEBUS] = None


class EBUSStation(BaseModel):
    """EBUS station characteristics and sampling."""
    station: str = Field(pattern=r'^(2R|2L|4R|4L|5|6|7|8|9|10R|10L|11R|11L|12R|12L|13R|13L|14R|14L)$')
    short_axis_mm: Optional[float] = None
    shape: Optional[Literal["oval", "round", "irregular"]] = None
    margin: Optional[Literal["distinct", "indistinct"]] = None
    echotexture: Optional[Literal["homogeneous", "heterogeneous"]] = None
    chs: Optional[Literal["present", "absent"]] = None
    cns: Optional[Literal["present", "absent"]] = None
    doppler: Optional[Literal["safe", "unsafe"]] = None
    elastography: Optional[Literal["predominantly_blue_stiff", "heterogeneous", "mostly_green_soft"]] = None
    sampled: bool = False
    passes: Optional[int] = None
    needle_gauge: Optional[Literal["21G", "22G", "25G"]] = None
    rose: Optional[Literal["adequate", "lymphoid", "malignant", "suspicious", "negative"]] = None


class EBUSInfo(BaseModel):
    """EBUS procedure information."""
    stations: List[EBUSStation] = Field(default_factory=list)


class TBNASample(BaseModel):
    """Transbronchial needle aspiration sample."""
    site: str
    gauge: Optional[str] = None
    passes: Optional[int] = None


class TBBXSample(BaseModel):
    """Transbronchial biopsy sample."""
    lobe: str
    segments: List[str] = Field(default_factory=list)
    forceps_bites: Optional[int] = None


class CryoBiopsySample(BaseModel):
    """Cryobiopsy sample."""
    probe_mm: Optional[float] = None
    freezes: Optional[int] = None
    freeze_sec: Optional[int] = None


class BrushSample(BaseModel):
    """Brush sample."""
    site: str
    passes: Optional[int] = None


class BALSample(BaseModel):
    """Bronchoalveolar lavage sample."""
    site: Optional[str] = None
    instilled_ml: Optional[float] = None
    returned_ml: Optional[float] = None
    appearance: Optional[Literal["clear", "turbid", "bloody"]] = None


class SamplingInfo(BaseModel):
    """All sampling modalities."""
    tbna: List[TBNASample] = Field(default_factory=list)
    tbbx: List[TBBXSample] = Field(default_factory=list)
    cryo_biopsy: List[CryoBiopsySample] = Field(default_factory=list)
    brush: List[BrushSample] = Field(default_factory=list)
    bal: Optional[BALSample] = None


class AblationTarget(BaseModel):
    """Ablation target location."""
    lobe: Optional[str] = None
    segment: Optional[str] = None
    distance_to_pleura_mm: Optional[float] = None


class AblationConfirmation(BaseModel):
    """Ablation targeting confirmation."""
    cbct: bool = False
    rebus: bool = False
    tool_in_lesion: bool = False


class AblationParameters(BaseModel):
    """Ablation energy parameters."""
    power_w: Optional[float] = None
    time_sec: Optional[float] = None
    cycles: Optional[int] = None
    freeze_thaw: Optional[List[float]] = None


class PostAblationImaging(BaseModel):
    """Post-ablation imaging."""
    cbct: bool = False
    fluoro: bool = False


class AblationInfo(BaseModel):
    """Ablation procedure information."""
    modality: Optional[Literal["MWA", "RFA", "Cryoablation", "PEF_IRE"]] = None
    system: Optional[str] = None
    target: Optional[AblationTarget] = None
    confirmation: Optional[AblationConfirmation] = None
    parameters: Optional[AblationParameters] = None
    ablations: Optional[int] = None
    post_imaging: Optional[PostAblationImaging] = None


class Thoracentesis(BaseModel):
    """Thoracentesis procedure."""
    side: Optional[str] = None
    us_guided: bool = False
    volume_ml: Optional[float] = None
    manometry_open: Optional[float] = None
    manometry_close: Optional[float] = None


class Pigtail(BaseModel):
    """Pigtail catheter placement."""
    indication: Optional[Literal["effusion", "ptx"]] = None
    size_fr: Optional[float] = None
    suction_cmH2O: Optional[float] = None


class IPC(BaseModel):
    """Indwelling pleural catheter."""
    placed: bool = False
    tunneled: bool = False
    size_fr: Optional[float] = None
    education_delivered: bool = False


class TalcPleurodesis(BaseModel):
    """Talc pleurodesis."""
    method: Optional[Literal["slurry", "poudrage"]] = None
    dose_g: Optional[float] = None
    graded: bool = False


class IPCFibrinolysis(BaseModel):
    """IPC fibrinolysis with tPA."""
    tpa_mg: Optional[float] = None
    diluent_ml: Optional[float] = None
    dwell_min: Optional[float] = None


class PleuralProcedures(BaseModel):
    """All pleural procedures."""
    thoracentesis: Optional[Thoracentesis] = None
    pigtail: Optional[Pigtail] = None
    ipc: Optional[IPC] = None
    talc_pleurodesis: Optional[TalcPleurodesis] = None
    ipc_fibrinolysis: Optional[IPCFibrinolysis] = None


class PDTInfo(BaseModel):
    """Percutaneous dilatational tracheostomy."""
    indication: Optional[Literal["prolonged_mechanical_ventilation", "airway_protection", "other"]] = None
    kit: Optional[Literal["Ciaglia_Blue_Rhino", "PercuTwist", "others"]] = None
    bronch_guided: bool = False
    rings_identified: bool = False
    needle_entry_confirmed: bool = False
    dilations: List[str] = Field(default_factory=list)
    final_tube_position_cm_above_carina: Optional[float] = None


class Pneumothorax(BaseModel):
    """Pneumothorax complication."""
    present: bool = False
    size: Optional[str] = None
    intervention: Optional[str] = None


class Bleeding(BaseModel):
    """Bleeding complication."""
    present: bool = False
    severity: Literal["none", "minor", "moderate", "brisk"] = "none"
    hemostasis: Optional[Literal["suction", "tamponade", "APC", "epi", "TXA"]] = None


class HypoxemiaIntervention(BaseModel):
    """Hypoxemia requiring intervention."""
    present: bool = False
    details: Optional[str] = None


class Complications(BaseModel):
    """Procedure complications."""
    pneumothorax: Optional[Pneumothorax] = None
    bleeding: Optional[Bleeding] = None
    hypoxemia_intervention: Optional[HypoxemiaIntervention] = None
    other: List[str] = Field(default_factory=list)


class Specimens(BaseModel):
    """Specimen collection and testing."""
    cell_block: bool = False
    molecular: List[Literal["EGFR", "ALK", "ROS1", "PDL1", "NGS"]] = Field(default_factory=list)
    microbiology: List[Literal["bacterial", "fungal", "AFB"]] = Field(default_factory=list)
    flow_cytometry: bool = False


class Followup(BaseModel):
    """Follow-up plan."""
    service: str
    when: str


class PostOpInfo(BaseModel):
    """Post-operative information."""
    diagnosis: Optional[str] = None
    ebl_ml: Optional[float] = None
    disposition: Optional[Literal["PACU", "ICU", "Ward"]] = None
    imaging_orders: List[Literal["none", "CXR_now", "CXR_in_4h"]] = Field(default_factory=list)
    followups: List[Followup] = Field(default_factory=list)


class IPProcedureReport(BaseModel):
    """Complete IP procedure report matching JSON Schema v1."""
    version: Literal["1.0"] = "1.0"
    procedure_key: Literal[
        "robotic_ion",
        "ebus_systematic_staging_ett",
        "pdt",
        "tma_mwa",
        "therapeutic_cryo_airway",
        "rigid_foreign_body",
        "talc_pleurodesis",
        "ipc_fibrinolysis",
        "bronch_nodule_ablation_generic",
        "standard_bronchoscopy",
        "ebus_staging",
        "navigation_bronchoscopy"
    ]
    patient: PatientInfo
    context: ProcedureContext
    anesthesia: Optional[AnesthesiaInfo] = None
    findings: Optional[Findings] = None
    devices: List[Device] = Field(default_factory=list)
    imaging_guidance: Optional[ImagingGuidance] = None
    ebus: Optional[EBUSInfo] = None
    sampling: Optional[SamplingInfo] = None
    ablation: Optional[AblationInfo] = None
    pleural: Optional[PleuralProcedures] = None
    pdt: Optional[PDTInfo] = None
    complications: Optional[Complications] = None
    specimens: Optional[Specimens] = None
    postop: Optional[PostOpInfo] = None

    class Config:
        """Pydantic configuration."""
        extra = "forbid"  # Equivalent to additionalProperties: false in JSON Schema
        validate_assignment = True
        use_enum_values = True

    def to_json_schema_compliant(self) -> dict:
        """Export to JSON Schema v1 compliant format."""
        return self.dict(exclude_none=True, by_alias=True)

    @classmethod
    def from_dict(cls, data: dict) -> "IPProcedureReport":
        """Create from dictionary with validation."""
        return cls(**data)