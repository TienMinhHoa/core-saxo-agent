"""Pure policies used by the legacy UI callbacks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from music_rag.agentic import AgenticRetriever, OpenAIRetrievalAgent
from music_rag.deepseek_answer import DeepSeekAnswerAgent
from music_rag.embeddings import OpenAIEmbeddingProvider
from music_rag.errors import MusicRagError


def select_chroma_records(response: object) -> list[dict[str, object]]:
    """Extract mapping records from a validated Chroma response shape."""
    if not isinstance(response, Mapping):
        return []
    items = response.get("items")
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes, bytearray)):
        return []
    return [
        record
        for item in items
        if isinstance(item, Mapping)
        and isinstance(record := item.get("record"), dict)
    ]


def handle_chroma_request(
    request: str,
    *,
    chroma_service: object,
    access_scope: str,
    render_results: object,
) -> tuple[str, str, list[tuple[str, str]]]:
    """Run the legacy Chroma UI workflow outside the root entrypoint."""
    request = request.strip()
    if not request:
        return "Nh蘯ｭp cﾃ｢u h盻淑 ﾄ黛ｻ・tﾃｬm trong header chunks.", "", []
    try:
        understood = chroma_service.understand_request(request)
        provider = OpenAIEmbeddingProvider()
        agent = OpenAIRetrievalAgent()
        result = AgenticRetriever(chroma_service, provider, agent).run(understood["query"], access_scope)
    except (MusicRagError, RuntimeError, ValueError):
        return "Chroma RAG chﾆｰa s蘯ｵn sﾃng. Ki盻ノ tra API key, collection vﾃ index.", "", []
    response = result.response
    if response is None:
        return "Khﾃｴng tﾃｬm th蘯･y header chunk phﾃｹ h盻｣p.", "", []
    records = select_chroma_records(response)
    if not records:
        return "Khﾃｴng tﾃｬm th蘯･y header chunk phﾃｹ h盻｣p.", "", []
    body, images = render_results(records)
    status = (
        "ﾄ静｣ ch盻肱 source chunk phﾃｹ h盻｣p; 蘯｣nh h盻｣p l盻・ﾄ柁ｰ盻｣c hi盻ハ th盻・bﾃｪn dﾆｰ盻嬖."
        if result.status == "selected"
        else "Khﾃｴng cﾃｳ candidate ﾄ妥｡p 盻ｩng ﾄ黛ｺｧy ﾄ黛ｻｧ; ﾄ疎ng hi盻ハ th盻・source chunk t盻奏 nh蘯･t 盻・vﾃｲng cu盻訴 cﾃｹng."
    )
    return status, body, images


def select_answer_records(
    response: object,
    final_hits: Sequence[object],
    *,
    max_final_hits: int = 3,
) -> list[dict[str, object]]:
    """Select unique evidence, preferring agent-selected response items."""
    if not isinstance(response, Mapping) or not isinstance(max_final_hits, int) or max_final_hits < 0:
        return []

    records: list[dict[str, object]] = []
    seen_ids: set[str] = set()

    items = response.get("items")
    if isinstance(items, Sequence) and not isinstance(items, (str, bytes, bytearray)):
        candidates: Sequence[object] = items
    else:
        candidates = ()
    for item in candidates:
        record = item.get("record") if isinstance(item, Mapping) else None
        if isinstance(record, dict) and isinstance(record.get("chunk_id"), str):
            chunk_id = record["chunk_id"]
            if chunk_id not in seen_ids:
                records.append(record)
                seen_ids.add(chunk_id)

    for record in final_hits[:max_final_hits]:
        if isinstance(record, dict) and isinstance(record.get("chunk_id"), str):
            chunk_id = record["chunk_id"]
            if chunk_id not in seen_ids:
                records.append(record)
                seen_ids.add(chunk_id)
    return records


def handle_answer_request(
    request: str,
    *,
    chroma_service: object,
    access_scope: str,
    render_results: object,
    format_cost: object,
) -> tuple[str, str, str, list[tuple[str, str]], str]:
    """Run answer synthesis from validated Chroma evidence."""
    request = request.strip()
    if not request:
        return "Nh蘯ｭp cﾃ｢u h盻淑 ﾄ黛ｻ・t盻貧g h盻｣p cﾃ｢u tr蘯｣ l盻拱.", "", "", [], ""
    try:
        understood = chroma_service.understand_request(request)
        provider = OpenAIEmbeddingProvider()
        selector = OpenAIRetrievalAgent()
        retrieval = AgenticRetriever(chroma_service, provider, selector).run(understood["query"], access_scope)
        response = retrieval.response
        if response is None:
            return "Khﾃｴng tﾃｬm th蘯･y source chunk phﾃｹ h盻｣p ﾄ黛ｻ・t盻貧g h盻｣p.", "", "", [], ""
        records = select_answer_records(response, retrieval.final_hits)
        if not records:
            return "Khﾃｴng cﾃｳ source chunk h盻｣p l盻・ﾄ黛ｻ・t盻貧g h盻｣p.", "", "", [], ""
        answer_result = DeepSeekAnswerAgent().answer(request, records)
    except (MusicRagError, RuntimeError, ValueError):
        return "Answer RAG chﾆｰa s蘯ｵn sﾃng. Ki盻ノ tra DEEPSEEK_API_KEY, OPENAI_API_KEY vﾃ Chroma index.", "", "", [], ""
    body, images = render_results(records)
    status = (
        "ﾄ静｣ t盻貧g h盻｣p t盻ｫ source chunk ﾄ柁ｰ盻｣c agent ch盻肱 vﾃ cﾃ｡c candidate g蘯ｧn nh蘯･t."
        if retrieval.status == "selected"
        else "ﾄ紳ng t盻貧g h盻｣p t盻奏 nh蘯･t 盻・vﾃｲng retrieval cu盻訴 cﾃｹng."
    )
    return status, answer_result["answer"], body, images, format_cost(answer_result)
