from jinja2 import Environment, FileSystemLoader, select_autoescape, Template
from pathlib import Path
from .schema import ReporterParseResult

def _env(template_dir: str):
    return Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(enabled_extensions=("j2",))
    )

def render(template_text: str, values: dict) -> str:
    """Simple template rendering for testing."""
    template = Template(template_text)
    return template.render(**values)

def render_report(parsed: ReporterParseResult, template_dir: str) -> str:
    env = _env(template_dir)
    tmpl = env.get_template("bronchoscopy.md.j2")
    return tmpl.render(d=parsed)