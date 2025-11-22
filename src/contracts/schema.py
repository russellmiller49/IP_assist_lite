from typing import List, Literal, Optional, Any, Dict
from pydantic import BaseModel, Field

class SectionNode(BaseModel):
    title: str
    level: int
    content: str
    children: List['SectionNode'] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

class TableData(BaseModel):
    id: str
    caption: Optional[str] = None
    data: List[List[str]] # Simplified representation
    metadata: Dict[str, Any] = Field(default_factory=dict)

class Chunk(BaseModel):
    id: str
    text: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    method: str = "smart"

class MedicalMetadata(BaseModel):
    title: Optional[str] = None
    authors: List[str] = Field(default_factory=list)
    publication_date: Optional[str] = None
    source: Optional[str] = None
    other: Dict[str, Any] = Field(default_factory=dict)
    # Article specific
    abstract: Optional[str] = None
    keywords: List[str] = Field(default_factory=list)
    clinical_trial_ids: List[str] = Field(default_factory=list)

class SafetyWarning(BaseModel):
    text: str
    severity: Literal["warning", "caution", "note", "danger"]
    location: Optional[str] = None

class ExtractionResult(BaseModel):
    schema_version: str = "2.0.0"
    doc_id: str
    doc_type: Literal["article", "ifu", "textbook"]
    
    content_hierarchy: List[SectionNode]
    
    # Content Stores
    paragraph_store: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    chunks: List[Chunk] = Field(default_factory=list)
    evidence_bank: Dict[str, Any] = Field(default_factory=dict)
    
    # Tables
    tables: List[TableData] = Field(default_factory=list)
    table_sentences: List[Dict[str, Any]] = Field(default_factory=list) # {text, table_id, ...}

    metadata: MedicalMetadata
    safety_warnings: List[SafetyWarning] # Critical for IFUs
    
    # Metrics
    metrics: Dict[str, Any] = Field(default_factory=dict, alias="_metrics")
    
    class Config:
        populate_by_name = True
