"""Strict selector-decision validation; free-form answer fields are rejected."""
from __future__ import annotations

from typing import Any

from .errors import ValidationError

STATUSES = {"selected", "needs_clarification", "no_match"}
REASON_CODES = {"difficulty_unknown", "constraint_unknown", "ambiguous_request", "no_approved_match"}
SELECTED_KEYS = {"status", "candidate_set_id", "selected_items", "evidence_block_ids"}
OTHER_KEYS = {"status", "candidate_set_id", "reason_code"}


def validate_decision(decision: Any, candidate_set: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(decision, dict) or decision.get("status") not in STATUSES:
        raise ValidationError("decision_status_invalid")
    if decision.get("candidate_set_id") != candidate_set["candidate_set_id"]:
        raise ValidationError("candidate_set_mismatch")
    status = decision["status"]
    required = SELECTED_KEYS if status == "selected" else OTHER_KEYS
    if set(decision) != required:
        raise ValidationError("decision_contract_invalid")
    if status != "selected":
        if decision["reason_code"] not in REASON_CODES:
            raise ValidationError("reason_code_invalid")
        return decision
    selected = decision["selected_items"]
    evidence = decision["evidence_block_ids"]
    if not isinstance(selected, list) or not 1 <= len(selected) <= 3 or not isinstance(evidence, list):
        raise ValidationError("selection_shape_invalid")
    allowed = {(entry["item_id"], entry["item_version"]): set(entry["evidence_block_ids"]) for entry in candidate_set["candidates"]}
    seen: set[tuple[str, int]] = set()
    all_evidence: set[str] = set()
    for entry in selected:
        if not isinstance(entry, dict) or set(entry) != {"item_id", "item_version"}:
            raise ValidationError("selected_item_contract_invalid")
        key = (entry["item_id"], entry["item_version"])
        if key not in allowed or key in seen:
            raise ValidationError("selected_item_not_in_candidate_set")
        seen.add(key)
        all_evidence.update(allowed[key])
    if not set(evidence).issubset(all_evidence):
        raise ValidationError("evidence_not_in_selected_source")
    return decision
