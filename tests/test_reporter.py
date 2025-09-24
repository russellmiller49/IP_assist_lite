from src.reporter.template_store import TemplateStore
from src.reporter.renderer import render

def test_load_and_render():
    store = TemplateStore("data/templates/ip_procedure_templates.yaml")
    cats = store.list_categories()
    assert len(cats) >= 5
    # pick first category/proc
    name, cpt = store.list_procedures(cats[0])[0]
    txt = store.get_template_text(cats[0], name)
    fields = store.extract_fields(txt)
    vals = {f.key: "TEST" for f in fields if f.kind == "text"}
    note = render(txt, vals)
    assert isinstance(note, str)
    assert len(note) > 20