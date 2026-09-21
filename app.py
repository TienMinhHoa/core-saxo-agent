#!/usr/bin/env python3
"""Public Gradio frontend for the music RAG catalog."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import gradio as gr
from dotenv import load_dotenv

from music_rag.chroma_chunks import DEFAULT_CHROMA_DIR, DEFAULT_COLLECTION
from music_rag.chroma_service import ChromaChunkService
from music_rag.ui_rendering import (
    chroma_asset_paths as chroma_asset_paths,
    format_answer_cost as _format_answer_cost,
    render_chroma_results as _render_chroma_results,
)
from music_rag.ui_workflows import handle_answer_request, handle_chroma_request


def create_app(
    catalog_path: str | Path,
    access_scope: str = "public",
    chroma_dir: str | Path | None = None,
    chroma_collection: str | None = None,
    chroma_limit: int = 10,
) -> gr.Blocks:
    """Create the Chroma/VLM source UI and the DeepSeek answer UI."""
    del catalog_path
    chroma_path = Path(chroma_dir or os.environ.get("MUSIC_RAG_CHROMA_DIR", DEFAULT_CHROMA_DIR))
    chroma_name = chroma_collection or os.environ.get("MUSIC_RAG_CHROMA_COLLECTION", DEFAULT_COLLECTION)
    chroma_service = ChromaChunkService(
        chroma_path, chroma_name, source_scope=access_scope, limit=chroma_limit
    )

    def ask_chroma(request: str) -> tuple[str, str, list[tuple[str, str]]]:
        return handle_chroma_request(
            request,
            chroma_service=chroma_service,
            access_scope=access_scope,
            render_results=_render_chroma_results,
        )

    def ask_answer(request: str) -> tuple[str, str, str, list[tuple[str, str]], str]:
        return handle_answer_request(
            request,
            chroma_service=chroma_service,
            access_scope=access_scope,
            render_results=_render_chroma_results,
            format_cost=_format_answer_cost,
        )

    css = """
    .source-item { border-top: 1px solid #ddd; margin-top: 1rem; padding-top: 1rem; }
    .chroma-hit { border-top: 1px solid #ddd; margin-top: 1rem; padding-top: 1rem; }
    .source-meta { color: #555; font-size: .9rem; }
    .source-item pre { white-space: pre-wrap; overflow-wrap: anywhere; font: inherit; }
    .chroma-hit pre { white-space: pre-wrap; overflow-wrap: anywhere; font: inherit; max-height: 32rem; overflow: auto; }
    """
    with gr.Blocks(title="Music Source Library", css=css, analytics_enabled=False) as demo:
        gr.Markdown("# Music Theory RAG\nChroma/VLM source RAG and DeepSeek answer RAG.")
        with gr.Tabs():
            with gr.Tab("Header Chroma/VLM RAG"):
                gr.Markdown("Search source chunks with Chroma and an agentic retrieval workflow.")
                with gr.Row():
                    chroma_request = gr.Textbox(label="Question")
                    chroma_button = gr.Button("Search Chroma", variant="primary")
                chroma_status = gr.Markdown("Enter a question to search header chunks.")
                chroma_html = gr.HTML(label="Header chunks and content")
                chroma_images = gr.Gallery(label="Figures", columns=2, object_fit="contain", height="auto")
                chroma_button.click(ask_chroma, inputs=chroma_request, outputs=[chroma_status, chroma_html, chroma_images], api_name="ask_chroma_rag")
                chroma_request.submit(ask_chroma, inputs=chroma_request, outputs=[chroma_status, chroma_html, chroma_images], api_name="ask_chroma_rag_submit")
            with gr.Tab("Answer RAG - DeepSeek Flash"):
                gr.Markdown("Retrieve source chunks and synthesize an answer.")
                with gr.Row():
                    answer_request = gr.Textbox(label="Question")
                    answer_button = gr.Button("Synthesize answer", variant="primary")
                answer_status = gr.Markdown("Enter a question to synthesize an answer.")
                answer_markdown = gr.Markdown(label="Answer")
                answer_sources = gr.HTML(label="Source chunks")
                answer_images = gr.Gallery(label="Source figures", columns=2, object_fit="contain", height="auto")
                answer_cost = gr.Markdown(label="Answer cost")
                answer_button.click(ask_answer, inputs=answer_request, outputs=[answer_status, answer_markdown, answer_sources, answer_images, answer_cost], api_name="ask_answer_rag")
                answer_request.submit(ask_answer, inputs=answer_request, outputs=[answer_status, answer_markdown, answer_sources, answer_images, answer_cost], api_name="ask_answer_rag_submit")
    return demo.queue(default_concurrency_limit=4, max_size=20)


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=Path(os.environ.get("MUSIC_RAG_CATALOG", "runtime/music-rag")))
    parser.add_argument("--access-scope", default=os.environ.get("MUSIC_RAG_ACCESS_SCOPE", "public"))
    parser.add_argument("--host", default=os.environ.get("GRADIO_SERVER_NAME", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("GRADIO_SERVER_PORT", "7860")))
    parser.add_argument("--share", action="store_true", default=os.environ.get("GRADIO_SHARE", "false").casefold() == "true")
    parser.add_argument("--chroma-dir", type=Path, default=Path(os.environ.get("MUSIC_RAG_CHROMA_DIR", DEFAULT_CHROMA_DIR)))
    parser.add_argument("--chroma-collection", default=os.environ.get("MUSIC_RAG_CHROMA_COLLECTION", DEFAULT_COLLECTION))
    parser.add_argument("--chroma-limit", type=int, default=10)
    args = parser.parse_args()
    auth_user = os.environ.get("MUSIC_RAG_AUTH_USER")
    auth_password = os.environ.get("MUSIC_RAG_AUTH_PASSWORD")
    if bool(auth_user) != bool(auth_password):
        parser.error("Set both MUSIC_RAG_AUTH_USER and MUSIC_RAG_AUTH_PASSWORD, or neither.")
    if args.chroma_limit < 1:
        parser.error("--chroma-limit must be positive")
    demo = create_app(args.catalog, args.access_scope, args.chroma_dir, args.chroma_collection, args.chroma_limit)
    demo.launch(server_name=args.host, server_port=args.port, share=args.share, auth=(auth_user, auth_password) if auth_user else None, allowed_paths=chroma_asset_paths(args.chroma_dir), show_error=False, strict_cors=True)


if __name__ == "__main__":
    main()
