"""IP Procedure Reporting Module.

This module implements evidence-based structured reporting following:
- RCS-18 criteria for operative note completeness
- Synoptic reporting best practices for speed and accuracy
- Digital proforma approach for mandatory field compliance
"""

from .schema_contract import IPProcedureReport
from .blocks import (
    PRE_PROCEDURE_CHECKLIST,
    ANESTHESIA_SEDATION_STANDARD,
    COMPLICATIONS_CHECKLIST,
    SynopticReportBuilder
)

__all__ = [
    'IPProcedureReport',
    'PRE_PROCEDURE_CHECKLIST',
    'ANESTHESIA_SEDATION_STANDARD',
    'COMPLICATIONS_CHECKLIST',
    'SynopticReportBuilder'
]