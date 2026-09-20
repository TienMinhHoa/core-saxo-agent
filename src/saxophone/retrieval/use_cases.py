"""Application use cases for retrieval."""

from __future__ import annotations

from collections.abc import Mapping

from .models import ChunkHit, EvidenceBundle
from .ports import ChunkRetriever


class RetrieveEvidence:
    """Turn ranked retrieval hits into the validated chat boundary DTO."""

    def __init__(self, retriever: ChunkRetriever) -> None:
        self._retriever = retriever

    async def execute(
        self,
        query: str,
        *,
        filters: Mapping[str, object] | None = None,
        limit: int = 10,
    ) -> EvidenceBundle:
        normalized_query = query.strip() if isinstance(query, str) else query
        hits = list(
            await self._retriever.search(
                normalized_query, filters=filters, limit=limit
            )
        )
        if not hits:
            return EvidenceBundle(
                normalized_query,
                "retrieval-v1",
                (),
                (),
                {},
                insufficiency_reason="no matching evidence",
            )

        retrieval_version = hits[0].retrieval_version
        if any(hit.retrieval_version != retrieval_version for hit in hits):
            raise ValueError("all hits must use one retrieval version")

        source_texts: dict[str, str] = {}
        image_refs: list[str] = []
        seen_images: set[str] = set()
        for hit in hits:
            document = hit.metadata.get("document")
            if not isinstance(document, str) or not document.strip():
                raise ValueError("retrieval hit is missing validated source text")
            source_texts[hit.chunk_ref] = document
            for image_ref in _image_refs(hit):
                if image_ref not in seen_images:
                    seen_images.add(image_ref)
                    image_refs.append(image_ref)

        return EvidenceBundle(
            normalized_query,
            retrieval_version,
            tuple(hits),
            tuple(hit.chunk_ref for hit in hits),
            source_texts,
            tuple(image_refs),
        )


def _image_refs(hit: ChunkHit) -> tuple[str, ...]:
    value = hit.metadata.get("image_refs", ())
    if isinstance(value, str):
        return (value,) if value.strip() else ()
    if isinstance(value, (list, tuple)):
        return tuple(item for item in value if isinstance(item, str) and item.strip())
    return ()
