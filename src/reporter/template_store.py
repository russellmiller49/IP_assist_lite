"""Template store for IP procedure templates."""
from __future__ import annotations

import yaml
import re
from pathlib import Path
from typing import Dict, List, Tuple, Any, NamedTuple


class FieldInfo(NamedTuple):
    """Information about a template field."""
    key: str
    kind: str


class TemplateStore:
    """Store and manage IP procedure templates."""
    
    def __init__(self, template_path: str):
        self.template_path = Path(template_path)
        self.templates = self._load_templates()
    
    def _load_templates(self) -> Dict[str, Any]:
        """Load templates from YAML file."""
        if not self.template_path.exists():
            return {}
        
        try:
            with open(self.template_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception:
            return {}
    
    def list_categories(self) -> List[str]:
        """List all template categories."""
        return list(self.templates.keys())
    
    def list_procedures(self, category: str) -> List[Tuple[str, str]]:
        """List procedures in a category as (name, cpt_code) tuples."""
        if category not in self.templates:
            return []
        
        procedures = []
        for proc_name, proc_data in self.templates[category].items():
            if isinstance(proc_data, dict) and 'cpt' in proc_data:
                procedures.append((proc_name, proc_data['cpt']))
            elif isinstance(proc_data, str):
                # Assume it's a template string, extract CPT from name or use placeholder
                procedures.append((proc_name, "00000"))
        
        return procedures
    
    def get_template_text(self, category: str, procedure: str) -> str:
        """Get template text for a specific procedure."""
        if category not in self.templates:
            return ""
        
        if procedure not in self.templates[category]:
            return ""
        
        proc_data = self.templates[category][procedure]
        if isinstance(proc_data, dict):
            return proc_data.get('template', '')
        elif isinstance(proc_data, str):
            return proc_data
        
        return ""
    
    def get_cpt_code(self, category: str, procedure: str) -> str:
        """Get CPT code for a specific procedure."""
        if category not in self.templates:
            return ""
        
        if procedure not in self.templates[category]:
            return ""
        
        proc_data = self.templates[category][procedure]
        if isinstance(proc_data, dict):
            return proc_data.get('cpt', '')
        
        return ""
    
    def extract_fields(self, template_text: str) -> List[FieldInfo]:
        """Extract field information from template text."""
        fields = []
        # Simple regex to find {{field}} patterns
        pattern = r'\{\{([^}]+)\}\}'
        matches = re.findall(pattern, template_text)
        
        for match in matches:
            # Simple field parsing - assume all are text fields for now
            field_name = match.strip()
            fields.append(FieldInfo(key=field_name, kind="text"))
        
        return fields
