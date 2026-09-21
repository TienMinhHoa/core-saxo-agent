from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from saxophone.documents.knowledge import KnowledgeChunk
from saxophone.documents.ports import KnowledgeRepository
from saxophone.platform.knowledge import JsonKnowledgeRepository


def _chunk(*, chunk_id: str = "chunk-1") -> KnowledgeChunk:
    return KnowledgeChunk(
        chunk_id=chunk_id,
        document_id="document-1",
        source_version="extract-v1",
        source_ref="knowledge://document-1/chunk-1",
        search_text="Harmony and chord construction",
        content_hash=hashlib.sha256(b"chunk").hexdigest(),
        page_start=2,
        page_end=3,
        heading_path=("Part III", "Harmony"),
        tags=("chord",),
        image_refs=("images/page-0002-01.jpg",),
        paragraph_count=2,
        image_count=1,
    )


def test_json_repository_round_trips_and_replaces_full_fidelity_chunk(
    tmp_path: Path,
) -> None:
    repository: KnowledgeRepository = JsonKnowledgeRepository(tmp_path)
    original = _chunk()
    replacement = replace(original, search_text="Updated source")

    asyncio.run(repository.upsert(original))
    assert asyncio.run(repository.get(original.chunk_id)) == original
    asyncio.run(repository.upsert(replacement))
    assert asyncio.run(repository.get(original.chunk_id)) == replacement


def test_json_repository_reports_missing_chunk(tmp_path: Path) -> None:
    repository = JsonKnowledgeRepository(tmp_path)

    with pytest.raises(FileNotFoundError):
        asyncio.run(repository.get("missing"))
    with pytest.raises(FileNotFoundError):
        asyncio.run(repository.delete("missing"))


def test_json_repository_rejects_tampered_identity(tmp_path: Path) -> None:
    repository = JsonKnowledgeRepository(tmp_path)
    chunk = _chunk()
    asyncio.run(repository.upsert(chunk))
    stored_path = next(tmp_path.glob("*.json"))
    payload = json.loads(stored_path.read_text(encoding="utf-8"))
    payload["chunk_id"] = "other-chunk"
    stored_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="chunk ID"):
        asyncio.run(repository.get(chunk.chunk_id))


def test_json_repository_writes_atomic_sidecar_without_temporary_files(
    tmp_path: Path,
) -> None:
    repository = JsonKnowledgeRepository(tmp_path)

    asyncio.run(repository.upsert(_chunk()))

    assert list(tmp_path.glob("*.tmp")) == []
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_json_repository_rejects_non_path_root() -> None:
    with pytest.raises(ValueError, match="root must be a Path"):
        JsonKnowledgeRepository("not-a-path")  # type: ignore[arg-type]


def test_json_repository_rejects_existing_file_root(tmp_path: Path) -> None:
    root_file = tmp_path / "knowledge.json"
    root_file.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="root must be a directory"):
        JsonKnowledgeRepository(root_file)


def test_json_repository_rejects_symbolic_link_root(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"symbolic links unavailable: {error}")

    with pytest.raises(ValueError, match="root must not be a symbolic link"):
        JsonKnowledgeRepository(link)


@pytest.mark.parametrize("operation", ["get", "delete"])
def test_json_repository_rechecks_root_before_read_or_delete(
    tmp_path: Path,
    operation: str,
) -> None:
    repository = JsonKnowledgeRepository(tmp_path / "root")
    chunk = _chunk()
    asyncio.run(repository.upsert(chunk))

    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"symbolic links unavailable: {error}")

    repository._root = link  # type: ignore[attr-defined]

    with pytest.raises(ValueError, match="root must not be a symbolic link"):
        if operation == "get":
            asyncio.run(repository.get(chunk.chunk_id))
        else:
            asyncio.run(repository.delete(chunk.chunk_id))


def test_json_repository_rechecks_root_after_directory_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = JsonKnowledgeRepository(tmp_path / "root")
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"symbolic links unavailable: {error}")

    original_mkdir = Path.mkdir

    def mkdir_and_redirect(path: Path, *args: object, **kwargs: object) -> None:
        original_mkdir(path, *args, **kwargs)
        if path == repository._root:  # type: ignore[attr-defined]
            repository._root = link  # type: ignore[attr-defined]

    monkeypatch.setattr(Path, "mkdir", mkdir_and_redirect)

    with pytest.raises(ValueError, match="root path must not contain a symbolic link"):
        asyncio.run(repository.upsert(_chunk()))
