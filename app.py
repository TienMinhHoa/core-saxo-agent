#!/usr/bin/env python3
"""Public Gradio frontend plus source-only backend for the music RAG catalog.

The app never imports a source document.  Run the reviewed import/publish
workflow first, then point MUSIC_RAG_CATALOG at that writable catalog.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

import gradio as gr
from dotenv import load_dotenv

from music_rag.agentic import AgenticRetriever, OpenAIRetrievalAgent
from music_rag.chroma_chunks import DEFAULT_CHROMA_DIR, DEFAULT_COLLECTION
from music_rag.chroma_service import ChromaChunkService
from music_rag.deepseek_answer import DeepSeekAnswerAgent
from music_rag.embeddings import OpenAIEmbeddingProvider
from music_rag.errors import MusicRagError


# Compatibility names remain stable while pure policy helpers live in the
# package namespace instead of being owned by the root entrypoint.
from music_rag.ui_rendering import (
    chroma_asset_paths as chroma_asset_paths,
    render_chroma_results as _render_chroma_results,
)


def _answer_cost_markdown(result: dict[str, Any]) -> str:
    usage = result["usage"]
    cost = result["cost"]
    estimated = " (ước lượng)" if not usage.get("available", False) else ""
    return "\n".join([
        "### Chi phí riêng của lượt tổng hợp",
        f"- Model: `{result['model']}` · thinking: enabled · effort: `{result['reasoning_effort']}`",
        (
            f"- Input: **{int(usage['input_tokens']):,}** token{estimated} "
            f"(cache hit {int(usage['cache_hit_tokens']):,}, miss {int(usage['cache_miss_tokens']):,})"
        ),
        (
            f"- Output: **{int(usage['output_tokens']):,}** token{estimated} "
            f"(reasoning {int(usage.get('reasoning_tokens', 0)):,})"
        ),
        f"- Khung giá: `{cost['period']}` (UTC) · ảnh gửi kèm: {result.get('image_inputs', 0)}",
        (
            f"- **Tổng chi phí trả lời: `${cost['total_usd']:.8f}`** "
            f"(input `${cost['input_usd']:.8f}`, output `${cost['output_usd']:.8f}`)"
        ),
        "> Chi phí này chỉ tính request tổng hợp DeepSeek, không tính embedding/retrieval.",
    ])


def create_app(
    catalog_path: str | Path,
    access_scope: str = "public",
    chroma_dir: str | Path | None = None,
    chroma_collection: str | None = None,
    chroma_limit: int = 10,
) -> gr.Blocks:
    """Create the Chroma/VLM source UI and the DeepSeek answer UI."""
    chroma_path = Path(chroma_dir or os.environ.get("MUSIC_RAG_CHROMA_DIR", DEFAULT_CHROMA_DIR))
    chroma_name = chroma_collection or os.environ.get("MUSIC_RAG_CHROMA_COLLECTION", DEFAULT_COLLECTION)
    chroma_service = ChromaChunkService(chroma_path, chroma_name, source_scope=access_scope, limit=chroma_limit)

    def ask_chroma(request: str) -> tuple[str, str, list[tuple[str, str]]]:
        request = request.strip()
        if not request:
            return "Nhập câu hỏi để tìm trong header chunks.", "", []
        try:
            understood = chroma_service.understand_request(request)
            provider = OpenAIEmbeddingProvider()
            agent = OpenAIRetrievalAgent()
            result = AgenticRetriever(chroma_service, provider, agent).run(understood["query"], access_scope)
        except (MusicRagError, RuntimeError, ValueError):
            return "Chroma RAG chưa sẵn sàng. Kiểm tra API key, collection và index.", "", []
        response = result.response
        if response is None:
            return "Không tìm thấy header chunk phù hợp.", "", []
        records = [item["record"] for item in response.get("items", []) if isinstance(item.get("record"), dict)]
        if not records:
            return "Không tìm thấy header chunk phù hợp.", "", []
        body, images = _render_chroma_results(records)
        status = (
            "Đã chọn source chunk phù hợp; ảnh hợp lệ được hiển thị bên dưới."
            if result.status == "selected"
            else "Không có candidate đáp ứng đầy đủ; đang hiển thị source chunk tốt nhất ở vòng cuối cùng."
        )
        return status, body, images

    def ask_answer(request: str) -> tuple[str, str, str, list[tuple[str, str]], str]:
        request = request.strip()
        if not request:
            return "Nhập câu hỏi để tổng hợp câu trả lời.", "", "", [], ""
        try:
            understood = chroma_service.understand_request(request)
            provider = OpenAIEmbeddingProvider()
            selector = OpenAIRetrievalAgent()
            retrieval = AgenticRetriever(chroma_service, provider, selector).run(understood["query"], access_scope)
            response = retrieval.response
            if response is None:
                return "Không tìm thấy source chunk phù hợp để tổng hợp.", "", "", [], ""
            records: list[dict[str, Any]] = []
            seen_ids: set[str] = set()
            # Include the agent-selected source first, then the other top
            # final-round hits so the answer model can synthesize across the
            # evidence that the retrieval agent inspected.
            for item in response.get("items", []):
                record = item.get("record") if isinstance(item, dict) else None
                chunk_id = record.get("chunk_id") if isinstance(record, dict) else None
                if isinstance(record, dict) and isinstance(chunk_id, str) and chunk_id not in seen_ids:
                    records.append(record)
                    seen_ids.add(chunk_id)
            for record in retrieval.final_hits[:3]:
                chunk_id = record.get("chunk_id") if isinstance(record, dict) else None
                if isinstance(record, dict) and isinstance(chunk_id, str) and chunk_id not in seen_ids:
                    records.append(record)
                    seen_ids.add(chunk_id)
            if not records:
                return "Không có source chunk hợp lệ để tổng hợp.", "", "", [], ""
            answer_result = DeepSeekAnswerAgent().answer(request, records)
        except (MusicRagError, RuntimeError, ValueError):
            return "Answer RAG chưa sẵn sàng. Kiểm tra DEEPSEEK_API_KEY, OPENAI_API_KEY và Chroma index.", "", "", [], ""
        body, images = _render_chroma_results(records)
        status = (
            "Đã tổng hợp từ source chunk được agent chọn và các candidate gần nhất."
            if retrieval.status == "selected"
            else "Đang tổng hợp từ source chunk tốt nhất ở vòng retrieval cuối cùng."
        )
        return status, answer_result["answer"], body, images, _answer_cost_markdown(answer_result)

    css = """
    .source-item { border-top: 1px solid #ddd; margin-top: 1rem; padding-top: 1rem; }
    .chroma-hit { border-top: 1px solid #ddd; margin-top: 1rem; padding-top: 1rem; }
    .source-meta { color: #555; font-size: .9rem; }
    .source-item pre { white-space: pre-wrap; overflow-wrap: anywhere; font: inherit; }
    .chroma-hit pre { white-space: pre-wrap; overflow-wrap: anywhere; font: inherit; max-height: 32rem; overflow: auto; }
    """
    with gr.Blocks(title="Music Source Library", css=css, analytics_enabled=False) as demo:
        gr.Markdown("# Music Theory RAG\nChroma/VLM source RAG và Answer RAG tổng hợp bằng DeepSeek Flash.")
        with gr.Tabs():
            with gr.Tab("Header Chroma/VLM RAG"):
                gr.Markdown("Search theo agentic RAG: embedding Chroma → candidate → agent đánh giá → rewrite/retry tối đa 4 vòng. Nếu chunk có ảnh VLM hợp lệ, ảnh được lấy từ sidecar và hiển thị trong Gallery với figure/caption/summary.")
                with gr.Row():
                    chroma_request = gr.Textbox(label="Câu hỏi", placeholder="Ví dụ: What is an eighth-note beam?")
                    chroma_button = gr.Button("Search Chroma", variant="primary")
                chroma_status = gr.Markdown("Nhập câu hỏi để tìm trong header chunks.")
                chroma_html = gr.HTML(label="Header chunks và nội dung")
                chroma_images = gr.Gallery(label="Figures trong kết quả", columns=2, object_fit="contain", height="auto")
                chroma_button.click(ask_chroma, inputs=chroma_request, outputs=[chroma_status, chroma_html, chroma_images], api_name="ask_chroma_rag")
                chroma_request.submit(ask_chroma, inputs=chroma_request, outputs=[chroma_status, chroma_html, chroma_images], api_name="ask_chroma_rag_submit")
            with gr.Tab("Answer RAG · DeepSeek Flash"):
                gr.Markdown("Giữ nguyên agentic retrieval trên Chroma, sau đó DeepSeek Flash đọc source chunks và tổng hợp câu trả lời. Thinking được bật; reasoning nội bộ không hiển thị.")
                with gr.Row():
                    answer_request = gr.Textbox(label="Câu hỏi", placeholder="Ví dụ: Explain how eighth-note beams work.")
                    answer_button = gr.Button("Tổng hợp câu trả lời", variant="primary")
                answer_status = gr.Markdown("Nhập câu hỏi để tổng hợp câu trả lời.")
                answer_markdown = gr.Markdown(label="Câu trả lời")
                answer_sources = gr.HTML(label="Source chunks được dùng")
                answer_images = gr.Gallery(label="Figures trong source", columns=2, object_fit="contain", height="auto")
                answer_cost = gr.Markdown(label="Chi phí lượt trả lời")
                answer_button.click(
                    ask_answer,
                    inputs=answer_request,
                    outputs=[answer_status, answer_markdown, answer_sources, answer_images, answer_cost],
                    api_name="ask_answer_rag",
                )
                answer_request.submit(
                    ask_answer,
                    inputs=answer_request,
                    outputs=[answer_status, answer_markdown, answer_sources, answer_images, answer_cost],
                    api_name="ask_answer_rag_submit",
                )
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
    # The UI now exposes only the Chroma/VLM source and answer tabs.  Catalog
    # asset paths are intentionally not added to Gradio's allow-list.
    allowed_paths = chroma_asset_paths(args.chroma_dir)
    demo.launch(
        server_name=args.host,
        server_port=args.port,
        share=args.share,
        auth=(auth_user, auth_password) if auth_user else None,
        allowed_paths=allowed_paths,
        show_error=False,
        strict_cors=True,
    )


if __name__ == "__main__":
    main()
