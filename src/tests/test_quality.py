"""Tests for quality validators."""

import pytest
from src.reporting.schema_contract import IPProcedureReport, PatientInfo, ProcedureContext, PostOpInfo, Complications
from src.reporting.quality import (
    validate_rcs18,
    validate_lidocaine_safety,
    validate_imaging_consistency,
    validate_ebus_completeness,
    validate_safety_critical,
    run_all_validators,
    get_validation_summary
)


class TestRCS18Validation:
    """Test RCS-18 compliance validation."""
    
    def test_complete_report_passes(self):
        """Test that complete report passes RCS-18."""
        report = IPProcedureReport(
            version="1.0",
            procedure_key="robotic_ion",
            patient=PatientInfo(name="Test", dod_id="123", dob="1950-01-01"),
            context=ProcedureContext(
                date="2024-01-15",
                location="OR",
                elective_vs_emergency="elective"
            ),
            postop=PostOpInfo(
                ebl_ml=5,
                disposition="PACU"
            ),
            complications=Complications()
        )
        
        issues = validate_rcs18(report)
        # Some fields still missing but core ones present
        assert len(issues) < 10
    
    def test_missing_date_fails(self):
        """Test that missing date is caught."""
        report = IPProcedureReport(
            version="1.0",
            procedure_key="robotic_ion",
            patient=PatientInfo(name="Test", dod_id="123", dob="1950-01-01"),
            context=ProcedureContext(
                date=None,  # Missing date
                location="OR",
                elective_vs_emergency="elective"
            )
        )
        
        issues = validate_rcs18(report)
        assert any("date" in issue.lower() for issue in issues)
    
    def test_missing_ebl_fails(self):
        """Test that missing EBL is caught."""
        report = IPProcedureReport(
            version="1.0",
            procedure_key="robotic_ion",
            patient=PatientInfo(name="Test", dod_id="123", dob="1950-01-01"),
            context=ProcedureContext(
                date="2024-01-15",
                location="OR",
                elective_vs_emergency="elective"
            )
            # Missing postop with EBL
        )
        
        issues = validate_rcs18(report)
        assert any("blood loss" in issue.lower() for issue in issues)


class TestLidocaineSafety:
    """Test lidocaine safety validation."""
    
    def test_safe_dose_passes(self):
        """Test that safe lidocaine dose passes."""
        from src.reporting.schema_contract import AnesthesiaInfo, TopicalLidocaine
        
        report = IPProcedureReport(
            version="1.0",
            procedure_key="robotic_ion",
            patient=PatientInfo(name="Test", dod_id="123", dob="1950-01-01"),
            context=ProcedureContext(date="2024-01-15", location="OR", elective_vs_emergency="elective"),
            anesthesia=AnesthesiaInfo(
                topical_lidocaine=TopicalLidocaine(
                    mg=60,
                    mg_per_kg=0.8
                )
            )
        )
        
        warnings = validate_lidocaine_safety(report)
        assert len(warnings) == 0
    
    def test_high_dose_warns(self):
        """Test that high lidocaine dose triggers warning."""
        from src.reporting.schema_contract import AnesthesiaInfo, TopicalLidocaine
        
        report = IPProcedureReport(
            version="1.0",
            procedure_key="robotic_ion",
            patient=PatientInfo(name="Test", dod_id="123", dob="1950-01-01"),
            context=ProcedureContext(date="2024-01-15", location="OR", elective_vs_emergency="elective"),
            anesthesia=AnesthesiaInfo(
                topical_lidocaine=TopicalLidocaine(
                    mg=600,  # High dose
                    mg_per_kg=8.5  # Over target
                )
            )
        )
        
        warnings = validate_lidocaine_safety(report)
        assert len(warnings) > 0
        assert any("500" in w for w in warnings)
        assert any("8 mg/kg" in w for w in warnings)


class TestSafetyCritical:
    """Test safety-critical validation."""
    
    def test_brisk_bleeding_without_hemostasis(self):
        """Test that brisk bleeding without hemostasis is critical."""
        from src.reporting.schema_contract import Bleeding
        
        report = IPProcedureReport(
            version="1.0",
            procedure_key="robotic_ion",
            patient=PatientInfo(name="Test", dod_id="123", dob="1950-01-01"),
            context=ProcedureContext(date="2024-01-15", location="OR", elective_vs_emergency="elective"),
            complications=Complications(
                bleeding=Bleeding(
                    present=True,
                    severity="brisk",
                    hemostasis=None  # No hemostasis documented
                )
            )
        )
        
        critical = validate_safety_critical(report)
        assert len(critical) > 0
        assert any("bleeding" in c.lower() for c in critical)
    
    def test_pneumothorax_without_intervention(self):
        """Test that PTX without intervention is critical."""
        from src.reporting.schema_contract import Pneumothorax
        
        report = IPProcedureReport(
            version="1.0",
            procedure_key="robotic_ion",
            patient=PatientInfo(name="Test", dod_id="123", dob="1950-01-01"),
            context=ProcedureContext(date="2024-01-15", location="OR", elective_vs_emergency="elective"),
            complications=Complications(
                pneumothorax=Pneumothorax(
                    present=True,
                    intervention=None  # No intervention documented
                )
            )
        )
        
        critical = validate_safety_critical(report)
        assert len(critical) > 0
        assert any("pneumothorax" in c.lower() for c in critical)


class TestValidationSummary:
    """Test validation summary generation."""
    
    def test_summary_formatting(self):
        """Test that summary is properly formatted."""
        results = {
            "rcs18": ["Missing date", "Missing EBL"],
            "safety_critical": ["CRITICAL: Pneumothorax without intervention"],
            "lidocaine": [],
            "imaging": [],
            "ebus": [],
            "specimens": []
        }
        
        summary = get_validation_summary(results)
        assert "CRITICAL SAFETY ISSUES" in summary
        assert "RCS-18 Compliance" in summary
        assert "16/18" in summary  # 18 - 2 issues
    
    def test_all_pass_summary(self):
        """Test summary when all checks pass."""
        results = {
            "rcs18": [],
            "safety_critical": [],
            "lidocaine": [],
            "imaging": [],
            "ebus": [],
            "specimens": []
        }
        
        summary = get_validation_summary(results)
        assert "All quality checks passed" in summary


if __name__ == "__main__":
    pytest.main([__file__, "-v"])