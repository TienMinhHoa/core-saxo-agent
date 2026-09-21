from __future__ import annotations

import asyncio
import json
import threading

import anyio
import pytest

from saxophone.tagging.models import TaggedParagraph
from saxophone.tagging.persistence import JsonTagCatalogRepository, JsonTaggedParagraphRepository
from saxophone.tagging.ports import TagCatalogRepository, TaggedParagraphRepository


class _TaggedParagraphStore:
    def __init__(self) -> None:
        self._items: dict[str, TaggedParagraph] = {}

    async def upsert(self, paragraph: TaggedParagraph) -> None:
        self._items[paragraph.paragraph_id] = paragraph

    async def get(self, paragraph_id: str) -> TaggedParagraph:
        try:
            return self._items[paragraph_id]
        except KeyError as error:
            raise FileNotFoundError(paragraph_id) from error

    async def delete(self, paragraph_id: str) -> None:
        try:
            del self._items[paragraph_id]
        except KeyError as error:
            raise FileNotFoundError(paragraph_id) from error


class _TagCatalog:
    def __init__(self) -> None:
        self._tags: set[str] = set()

    async def add(self, tags: tuple[str, ...]) -> None:
        self._tags.update(tags)

    async def list(self) -> tuple[str, ...]:
        return tuple(sorted(self._tags))


def _paragraph(*, text: str = "Harmony source") -> TaggedParagraph:
    return TaggedParagraph(
        paragraph_id="chunk-1:p0000",
        text=text,
        generated_tags=("Concept of harmony",),
        tags=("Harmony definition",),
        status="completed",
    )


def test_tagged_paragraph_repository_is_source_preserving_and_replaceable() -> None:
    repository: TaggedParagraphRepository = _TaggedParagraphStore()
    original = _paragraph()
    replacement = _paragraph(text="Updated harmony source")

    asyncio.run(repository.upsert(original))
    assert asyncio.run(repository.get(original.paragraph_id)) == original
    asyncio.run(repository.upsert(replacement))
    assert asyncio.run(repository.get(original.paragraph_id)).text == "Updated harmony source"


def test_tagged_paragraph_repository_reports_missing_records() -> None:
    repository: TaggedParagraphRepository = _TaggedParagraphStore()

    with pytest.raises(FileNotFoundError):
        asyncio.run(repository.get("missing"))
    with pytest.raises(FileNotFoundError):
        asyncio.run(repository.delete("missing"))


def test_tag_catalog_is_deterministic_and_deduplicated() -> None:
    catalog: TagCatalogRepository = _TagCatalog()

    asyncio.run(catalog.add(("Harmony definition", "Chord construction")))
    asyncio.run(catalog.add(("Harmony definition",)))

    assert asyncio.run(catalog.list()) == ("Chord construction", "Harmony definition")


def test_json_tagged_paragraph_repository_round_trips_and_replaces(tmp_path) -> None:
    repository = JsonTaggedParagraphRepository(tmp_path / "paragraphs")
    original = _paragraph()
    replacement = _paragraph(text="Updated harmony source")

    asyncio.run(repository.upsert(original))
    assert asyncio.run(repository.get(original.paragraph_id)) == original
    asyncio.run(repository.upsert(replacement))

    assert asyncio.run(repository.get(original.paragraph_id)) == replacement


def test_json_tagged_paragraph_repository_rejects_tampered_identity(tmp_path) -> None:
    repository = JsonTaggedParagraphRepository(tmp_path / "paragraphs")
    paragraph = _paragraph()
    asyncio.run(repository.upsert(paragraph))
    stored = next((tmp_path / "paragraphs").glob("*.json"))
    payload = json.loads(stored.read_text(encoding="utf-8"))
    payload["paragraph_id"] = "other"
    stored.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="paragraph ID"):
        asyncio.run(repository.get(paragraph.paragraph_id))


def test_json_tagged_paragraph_repository_delete_resolves_path_in_worker(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = JsonTaggedParagraphRepository(tmp_path / "paragraphs")
    paragraph = _paragraph()
    asyncio.run(repository.upsert(paragraph))

    caller_thread = threading.get_ident()
    observed_threads: list[int] = []
    real_path_for = repository._path_for

    def observe_path_for(paragraph_id: str):
        observed_threads.append(threading.get_ident())
        return real_path_for(paragraph_id)

    monkeypatch.setattr(repository, "_path_for", observe_path_for)

    asyncio.run(repository.delete(paragraph.paragraph_id))

    assert observed_threads
    assert all(thread_id != caller_thread for thread_id in observed_threads)


def test_json_tag_catalog_is_atomic_and_deterministic(tmp_path) -> None:
    catalog = JsonTagCatalogRepository(tmp_path / "tags.json")

    asyncio.run(catalog.add(("Harmony definition", "Chord construction")))
    asyncio.run(catalog.add(("Harmony definition",)))

    assert asyncio.run(catalog.list()) == ("Chord construction", "Harmony definition")


def test_json_tag_repositories_accept_a_shared_bounded_io_limiter(tmp_path) -> None:
    limiter = anyio.CapacityLimiter(1)

    paragraph_repository = JsonTaggedParagraphRepository(
        tmp_path / "paragraphs",
        io_limiter=limiter,
    )
    catalog_repository = JsonTagCatalogRepository(
        tmp_path / "tags.json",
        io_limiter=limiter,
    )

    assert paragraph_repository._io_limiter is limiter
    assert catalog_repository._io_limiter is limiter


def test_json_tagged_paragraph_repository_rejects_file_root(tmp_path) -> None:
    root = tmp_path / "paragraphs.json"
    root.write_text("not a directory", encoding="utf-8")

    with pytest.raises(ValueError, match="root must be a directory"):
        JsonTaggedParagraphRepository(root)


def test_json_tagged_paragraph_repository_rechecks_root_before_read(tmp_path) -> None:
    root = tmp_path / "paragraphs"
    repository = JsonTaggedParagraphRepository(root)
    paragraph = _paragraph()
    asyncio.run(repository.upsert(paragraph))

    redirected = tmp_path / "redirected"
    redirected.mkdir()
    try:
        next(root.glob("*.json")).unlink()
        root.rmdir()
        root.symlink_to(redirected, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links are unavailable in this environment")

    with pytest.raises(ValueError, match="symbolic link"):
        asyncio.run(repository.get(paragraph.paragraph_id))


def test_json_tag_catalog_rejects_symbolic_link_parent(tmp_path) -> None:
    parent = tmp_path / "catalog-parent"
    redirected = tmp_path / "redirected"
    redirected.mkdir()
    try:
        parent.symlink_to(redirected, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links are unavailable in this environment")

    with pytest.raises(ValueError, match="symbolic link"):
        JsonTagCatalogRepository(parent / "tags.json")
