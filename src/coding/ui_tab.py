"""Gradio tab for V3 coding module with Q&A and copy-ready outputs."""

import gradio as gr
from .kb import CodingKB
from .extractors import extract_case
from .rules import code_case
from .formatter import to_markdown, to_copy_string
from .qa import build_context, answer as answer_q


def build():
    kb = CodingKB()  # load KB (auto-fallback between files)

    with gr.Tab("📋 Procedural Coding"):
        gr.Markdown(
            """
            ### V3 Procedural Coding Assistant
            Paste a procedure report to extract candidate CPTs, OPPS notes, documentation checks, and PCS suggestions. Use the Q&A box to ask follow‑ups (e.g., "Why 31653?", "OPPS packaging?", "PCS?").
            """
        )

        # Persistent state for follow‑ups
        ctx_state = gr.State(None)
        bundle_state = gr.State(None)

        with gr.Row():
            with gr.Column(scale=5):
                report = gr.Textbox(label="Procedure Report", lines=12, placeholder="Paste report text…")
                with gr.Row():
                    analyze = gr.Button("🔍 Analyze", variant="primary")
                    clear_btn = gr.Button("🧹 Clear")
                gr.Markdown(f"KB: {kb.version_info()}")

                gr.Markdown("""
                #### Follow‑up Q&A
                Ask about selected codes, OPPS/facility packaging, documentation, PCS suggestions, or NCCI/modifiers.
                """)
                qa_in = gr.Textbox(label="Question", placeholder="Why 31653? What about OPPS packaging?")
                qa_btn = gr.Button("💬 Answer")
                qa_out = gr.Markdown(label="Answer")

            with gr.Column(scale=7):
                analysis_md = gr.Markdown(label="Analysis")
                with gr.Row():
                    copy_format = gr.Dropdown(
                        label="Copy format",
                        choices=["simple", "detailed", "billing"],
                        value="simple",
                        scale=2,
                    )
                copy_box = gr.Textbox(label="Copy‑ready codes", lines=3)
                summary_json = gr.JSON(label="Summary")

        # --- Handlers ---
        def run_analysis(text: str):
            text = (text or "").strip()
            if not text:
                # No change to states; return empties
                return "Please paste a report.", "", {}, None, None
            case = extract_case(text, kb)
            bundle = code_case(case, kb)
            md = to_markdown(bundle)
            copy_str = to_copy_string(bundle, "simple")
            ctx = build_context(case, bundle, kb)
            # Return: analysis_md, copy_box, summary_json, ctx_state, bundle_state
            summary = {
                "total_professional": len(bundle.professional),
                "total_facility": len(bundle.facility),
                "warnings": len(bundle.warnings),
                "documentation_gaps": len(bundle.documentation_gaps),
                "pcs_suggestions": len(bundle.icd10_pcs_suggestions),
                "codes": [cl.code for cl in bundle.professional] + [cl.code for cl in bundle.facility],
            }
            return md, copy_str, summary, ctx, bundle

        def update_copy(fmt: str, bundle):
            if not bundle:
                return ""
            return to_copy_string(bundle, fmt or "simple")

        def do_qa(q: str, ctx):
            q = (q or "").strip()
            if not q:
                return "Please enter a question."
            if not ctx:
                return "Run an analysis first, then ask a follow‑up."
            try:
                return answer_q(q, ctx)
            except Exception as e:
                return f"Error answering question: {e}"

        def do_clear():
            return "", "", {}, None, None, "", ""

        analyze.click(
            run_analysis,
            inputs=[report],
            outputs=[analysis_md, copy_box, summary_json, ctx_state, bundle_state],
        )
        copy_format.change(update_copy, inputs=[copy_format, bundle_state], outputs=[copy_box])
        qa_btn.click(do_qa, inputs=[qa_in, ctx_state], outputs=[qa_out])
        clear_btn.click(
            do_clear,
            inputs=[],
            outputs=[report, analysis_md, summary_json, ctx_state, bundle_state, copy_box, qa_out],
        )

    return None  # Tab is created in place
