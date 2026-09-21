from __future__ import annotations

from pathlib import Path

import pytest

from music_rag.chroma_service import ChromaChunkService
from music_rag.errors import NotFound


def _symlink_or_skip(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=target.is_dir())
    except OSError as exc:
        if getattr(exc, "winerror", None) == 1314:
            pytest.skip("Windows test account cannot create symbolic links")
        raise


def test_asset_path_rejects_symbolic_link_sidecar_before_read(tmp_path: Path) -> None:
    redirected = tmp_path / "redirected"
    redirected.mkdir()
    (redirected / "chunk-records.json").write_text("{}", encoding="utf-8")
    persist_dir = tmp_path / "chroma"
    _symlink_or_skip(persist_dir, redirected)

    service = ChromaChunkService(persist_dir, "collection")
    with pytest.raises(NotFound, match="chroma_sidecar_missing"):
        service.asset_path("chunk-1", 1, "chunk-1:asset:0", "public")


def test_asset_path_rejects_symbolic_link_sidecar_file_before_read(tmp_path: Path) -> None:
    persist_dir = tmp_path / "chroma"
    persist_dir.mkdir()
    redirected = tmp_path / "redirected.json"
    redirected.write_text("{}", encoding="utf-8")
    _symlink_or_skip(persist_dir / "chunk-records.json", redirected)

    service = ChromaChunkService(persist_dir, "collection")
    with pytest.raises(NotFound, match="chroma_sidecar_missing"):
        service.asset_path("chunk-1", 1, "chunk-1:asset:0", "public")


def test_asset_path_fails_closed_when_sidecar_becomes_symbolic_link(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    persist_dir = tmp_path / "chroma"
    persist_dir.mkdir()
    sidecar = persist_dir / "chunk-records.json"
    sidecar.write_text("{}", encoding="utf-8")
    original_is_symlink = Path.is_symlink

    def simulated_symlink(candidate: Path) -> bool:
        return candidate == sidecar or original_is_symlink(candidate)

    monkeypatch.setattr(Path, "is_symlink", simulated_symlink)
    service = ChromaChunkService(persist_dir, "collection")
    with pytest.raises(NotFound, match="chroma_sidecar_missing"):
        service.asset_path("chunk-1", 1, "chunk-1:asset:0", "public")
