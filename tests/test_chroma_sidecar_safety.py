from __future__ import annotations

from pathlib import Path

import pytest

import music_rag.chroma_chunks as chroma_chunks


def _symlink_or_skip(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=target.is_dir())
    except OSError as exc:
        if getattr(exc, "winerror", None) == 1314:
            pytest.skip("Windows test account cannot create symbolic links")
        raise


def test_sidecar_writer_rejects_symbolic_link_parent(tmp_path: Path) -> None:
    redirected = tmp_path / "redirected"
    redirected.mkdir()
    parent = tmp_path / "sidecars"
    _symlink_or_skip(parent, redirected)

    with pytest.raises(ValueError, match="symbolic link"):
        chroma_chunks._write_json(parent / "chunks.json", {"ok": True})


def test_sidecar_writer_rejects_symbolic_link_target(tmp_path: Path) -> None:
    target = tmp_path / "real.json"
    target.write_text("{}", encoding="utf-8")
    link = tmp_path / "chunks.json"
    _symlink_or_skip(link, target)

    with pytest.raises(ValueError, match="symbolic link"):
        chroma_chunks._write_json(link, {"ok": True})


def test_sidecar_writer_rechecks_path_before_replace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "chunks.json"
    original_validate = chroma_chunks._validate_json_path
    calls = 0
    replace_called = False

    def validate(candidate: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 3:
            raise ValueError("sidecar path changed before replace")
        original_validate(candidate)

    def unexpected_replace(source: str, destination: Path) -> None:
        nonlocal replace_called
        replace_called = True
        raise AssertionError("unsafe replace must not run after path re-check failure")

    monkeypatch.setattr(chroma_chunks, "_validate_json_path", validate)
    monkeypatch.setattr(chroma_chunks.os, "replace", unexpected_replace)

    with pytest.raises(ValueError, match="changed before replace"):
        chroma_chunks._write_json(path, {"ok": True})

    assert replace_called is False
    assert not path.exists()
