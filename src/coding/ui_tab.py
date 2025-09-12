"""Gradio tab for V3 coding module with Q&A."""

import gradio as gr
from .kb import CodingKB
from .extractors import extract_case
from .rules import code_case
from .formatter import to_markdown
from .qa import build_context, answer as answer_q

def build():
    kb = CodingKB()
    with gr.Tab("📋 Procedural Coding"):
        gr.Markdown("Paste a procedure report. You'll get CPT/HCPCS with rationales, OPPS/PCS notes, and doc checks. Ask follow‑ups below.")

        report = gr.Textbox(label="Procedure Report", lines=16, placeholder="Paste full report text...")
        md_out = gr.Markdown()
        codes_copy = gr.Textbox(label="Copy‑ready codes")
        analyze = gr.Button("🔍 Analyze", variant="primary")

        # Simplified Q&A panel
        qa_chat = gr.Chatbot(label="Ask about the rationale", height=250)
        qa_in = gr.Textbox(placeholder="e.g., Why 31653? Is +31627 packaged under OPPS?", label="Your question")
        qa_send = gr.Button("Ask")

        def _analyze(text):
            import json
            case = extract_case(text, kb, llm=None)
            bundle = code_case(case, kb)
            ctx = build_context(case, bundle, kb=kb)
            md = to_markdown(bundle) + f"\n\n_KB: {kb.version_info()}_"
            # Return simplified output without context for now
            return md, ", ".join(ctx["codes"]), [("System", "Analysis complete. Ask about any code or topic.")]

        def _qa_ask(msg, chat):
            return chat + [("System", "Q&A temporarily disabled for debugging.")]

        analyze.click(_analyze, inputs=[report], outputs=[md_out, codes_copy, qa_chat])
        qa_send.click(_qa_ask, inputs=[qa_in, qa_chat], outputs=[qa_chat])
    
    return None  # Tab is created in place