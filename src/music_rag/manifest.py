"""Strict manifest validation and publication checks for reviewed content items."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from .errors import ValidationError
from .store import CatalogStore
from .util import normalise_for_search

ITEM_TYPES = {"exercise", "exercise_group", "guideline"}
STATUSES = {"draft", "needs_review", "approved"}
MANIFEST_KEYS = {"document_id", "source_version", "items"}
ITEM_KEYS = {
    "item_id", "item_version", "section_id", "item_type", "content_block_ids",
    "required_context_refs", "verified_fields", "review_status",
}
REF_KEYS = {"item_id", "item_version", "evidence_block_id"}
VERIFIED_FIELD_KEYS = {"value", "evidence_block_id", "review_status"}


def _strict_keys(value: dict[str, Any], allowed: set[str], where: str) -> None:
    unknown = set(value) - allowed
    missing = allowed - set(value)
    if unknown or missing:
        raise ValidationError(f"{where}_keys_invalid: unknown={sorted(unknown)} missing={sorted(missing)}")


def validate_manifest_shape(manifest: dict[str, Any]) -> None:
    _strict_keys(manifest, MANIFEST_KEYS, "manifest")
    if not isinstance(manifest["items"], list):
        raise ValidationError("items_must_be_list")
    ids: set[tuple[str, int]] = set()
    for index, item in enumerate(manifest["items"]):
        if not isinstance(item, dict):
            raise ValidationError(f"item_{index}_must_be_object")
        _strict_keys(item, ITEM_KEYS, f"item_{index}")
        key = (item["item_id"], item["item_version"])
        if not isinstance(key[0], str) or not isinstance(key[1], int) or key in ids:
            raise ValidationError(f"item_{index}_identity_invalid")
        ids.add(key)
        if item["item_type"] not in ITEM_TYPES or item["review_status"] not in STATUSES:
            raise ValidationError(f"item_{index}_enum_invalid")
        if not isinstance(item["content_block_ids"], list) or not item["content_block_ids"]:
            raise ValidationError(f"item_{index}_content_blocks_invalid")
        if not isinstance(item["verified_fields"], dict):
            raise ValidationError(f"item_{index}_verified_fields_invalid")
        for field_name, field_value in item["verified_fields"].items():
            if not isinstance(field_name, str) or not isinstance(field_value, dict):
                raise ValidationError(f"item_{index}_verified_field_invalid")
            _strict_keys(field_value, VERIFIED_FIELD_KEYS, f"item_{index}_verified_field")
            if field_value["review_status"] != "approved" or not isinstance(field_value["evidence_block_id"], str):
                raise ValidationError(f"item_{index}_verified_field_evidence_invalid")
        if not isinstance(item["required_context_refs"], list):
            raise ValidationError(f"item_{index}_context_refs_invalid")
        for ref in item["required_context_refs"]:
            if not isinstance(ref, dict):
                raise ValidationError(f"item_{index}_context_ref_invalid")
            _strict_keys(ref, REF_KEYS, f"item_{index}_context_ref")


def _item_key(item: dict[str, Any]) -> str:
    return f"{item['item_id']}:{item['item_version']}"


def validate_manifest_against_catalog(store: CatalogStore, manifest: dict[str, Any]) -> list[str]:
    """Validate source/version/asset/dependency integrity without publishing."""
    validate_manifest_shape(manifest)
    catalog = store.load()
    document_key = f"{manifest['document_id']}:{manifest['source_version']}"
    document = catalog["documents"].get(document_key)
    if document is None:
        raise ValidationError("document_version_not_imported")
    all_items = dict(catalog["items"])
    staged = {_item_key(item): item for item in manifest["items"]}
    all_items.update(staged)
    errors: list[str] = []
    graph: dict[str, list[str]] = defaultdict(list)
    for key, item in staged.items():
        previous = catalog["items"].get(key)
        if previous is not None:
            comparison = dict(previous)
            comparison.pop("search_text", None)
            expected = dict(item)
            expected["document_id"] = manifest["document_id"]
            expected["source_version"] = manifest["source_version"]
            # A reviewer may move an otherwise identical item through the
            # workflow without changing its immutable item version.
            comparison.pop("review_status", None)
            expected.pop("review_status", None)
            if comparison != expected:
                errors.append(f"{key}:item_version_conflict")
        block_ids = item["content_block_ids"]
        blocks = [catalog["blocks"].get(block_id) for block_id in block_ids]
        if any(block is None for block in blocks):
            errors.append(f"{key}:content_block_missing")
            continue
        if len(set(block_ids)) != len(block_ids):
            errors.append(f"{key}:content_block_duplicate")
        if any(block["document_id"] != manifest["document_id"] or block["source_version"] != manifest["source_version"] for block in blocks):
            errors.append(f"{key}:block_version_mismatch")
        if [block["source_order"] for block in blocks] != sorted(block["source_order"] for block in blocks):
            errors.append(f"{key}:block_order_invalid")
        section = catalog["sections"].get(item["section_id"])
        if section is None:
            errors.append(f"{key}:section_missing")
        elif section["document_id"] != manifest["document_id"] or section["source_version"] != manifest["source_version"]:
            errors.append(f"{key}:section_version_mismatch")
        for field in item["verified_fields"].values():
            if field["evidence_block_id"] not in block_ids:
                errors.append(f"{key}:verified_field_evidence_invalid")
        for block in blocks:
            if block["kind"] == "asset" and not block.get("asset_path"):
                errors.append(f"{key}:asset_missing")
            elif block["kind"] == "asset":
                from pathlib import Path
                from .util import sha256_file
                path = Path(block["asset_path"])
                if not path.is_file() or sha256_file(path) != block["asset_hash"]:
                    errors.append(f"{key}:asset_checksum_invalid")
        for ref in item["required_context_refs"]:
            dependency = f"{ref['item_id']}:{ref['item_version']}"
            graph[key].append(dependency)
            target = all_items.get(dependency)
            evidence = catalog["blocks"].get(ref["evidence_block_id"])
            if target is None:
                errors.append(f"{key}:dependency_missing")
            elif target.get("review_status") != "approved":
                errors.append(f"{key}:dependency_not_approved")
            elif evidence is None or evidence["block_id"] not in block_ids:
                errors.append(f"{key}:dependency_evidence_invalid")
            elif not _same_access_scope(catalog, document, target, manifest):
                errors.append(f"{key}:dependency_scope_invalid")
    visiting: set[str] = set()
    visited: set[str] = set()
    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        cyclic = any(visit(child) for child in graph[node] if child in graph)
        visiting.remove(node)
        visited.add(node)
        return cyclic
    if any(visit(node) for node in graph):
        errors.append("dependency_cycle")
    return errors


def _same_access_scope(catalog: dict[str, Any], source_document: dict[str, Any], target: dict[str, Any], manifest: dict[str, Any]) -> bool:
    """Dependencies may cross documents, but never access scopes or versions."""
    target_document_id = target.get("document_id", manifest["document_id"])
    target_source_version = target.get("source_version", manifest["source_version"])
    target_document = catalog["documents"].get(f"{target_document_id}:{target_source_version}")
    return target_document is not None and target_document.get("access_scope") == source_document.get("access_scope")


def apply_manifest(store: CatalogStore, manifest: dict[str, Any]) -> list[str]:
    """Persist manifest items only after all validation passes."""
    errors = validate_manifest_against_catalog(store, manifest)
    if errors:
        return errors
    catalog = store.load()
    for source_item in manifest["items"]:
        item = dict(source_item)
        item["document_id"] = manifest["document_id"]
        item["source_version"] = manifest["source_version"]
        item["search_text"] = _source_search_text(catalog, item)
        catalog["items"][_item_key(item)] = item
    store.save(catalog)
    return []


def _source_search_text(catalog: dict[str, Any], item: dict[str, Any]) -> str:
    section = catalog["sections"].get(item["section_id"], {})
    text = [section.get("title_raw", "")]
    for block_id in item["content_block_ids"]:
        block = catalog["blocks"][block_id]
        if block["kind"] != "asset":
            text.append(block["raw_text"])
    # Verified values remain evidence-backed metadata; no LLM synthesis occurs.
    text.extend(str(value.get("value", "")) for value in item["verified_fields"].values() if isinstance(value, dict))
    return normalise_for_search(" ".join(text))
