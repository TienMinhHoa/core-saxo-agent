from __future__ import annotations

from pathlib import Path

import pytest

from music_rag.store import CatalogStore, EMPTY_CATALOG


def _symlink_or_skip(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=target.is_dir())
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symbolic links are unavailable: {exc}")


def test_store_rejects_root_that_is_a_file(tmp_path: Path) -> None:
    root = tmp_path / "catalog-root"
    root.write_text("not a directory", encoding="utf-8")

    with pytest.raises(ValueError, match="root must be a directory"):
        CatalogStore(root).save(EMPTY_CATALOG)


def test_store_rechecks_root_before_save_when_it_becomes_symlink(tmp_path: Path) -> None:
    root = tmp_path / "catalog-root"
    root.mkdir()
    redirected = tmp_path / "redirected"
    redirected.mkdir()
    store = CatalogStore(root)
    root.rmdir()
    _symlink_or_skip(root, redirected)

    with pytest.raises(ValueError, match="symbolic link"):
        store.save(EMPTY_CATALOG)

    assert not (redirected / "catalog.json").exists()


def test_store_rejects_catalog_file_symbolic_link(tmp_path: Path) -> None:
    root = tmp_path / "catalog-root"
    root.mkdir()
    redirected = tmp_path / "redirected.json"
    redirected.write_text("{}", encoding="utf-8")
    _symlink_or_skip(root / "catalog.json", redirected)

    with pytest.raises(ValueError, match="symbolic link"):
        CatalogStore(root).save(EMPTY_CATALOG)

    assert json_text(redirected) == "{}"


def json_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")
