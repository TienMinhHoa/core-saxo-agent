from __future__ import annotations

import pytest

from saxophone.tagging.models import (
    ExistingTagCandidate,
    TagConflictResolution,
    TagConflictResolutionRequest,
)
from saxophone.tagging.ports import TagConflictResolver


def test_resolution_keeps_generated_tag_or_reuses_a_candidate() -> None:
    request = TagConflictResolutionRequest(
        paragraph_id="chunk-1:p0001",
        generated_tags=("Concept of harmony", "Harmonics"),
        existing_tags=(
            ExistingTagCandidate(tag="Harmony definition", examples=("ch-2:p0003",)),
            ExistingTagCandidate(tag="Harmony", examples=("ch-9:p0001",)),
        ),
        resolution_profile="tag-conflicts-v1",
    )

    result = TagConflictResolution(
        paragraph_id=request.paragraph_id,
        resolutions=(
            ("Concept of harmony", "reuse_existing", "Harmony definition"),
            ("Harmonics", "keep_new", "Harmonics"),
        ),
        resolution_profile=request.resolution_profile,
        generated_tags=request.generated_tags,
        existing_tags=tuple(candidate.tag for candidate in request.existing_tags),
    )

    assert result.resolutions[0].action == "reuse_existing"
    assert result.resolutions[1].resolved_tag == "Harmonics"


def test_reuse_existing_must_reference_a_candidate() -> None:
    with pytest.raises(ValueError, match="existing tag candidate"):
        TagConflictResolution(
            paragraph_id="p-1",
            resolutions=(("Concept", "reuse_existing", "Not a candidate"),),
            resolution_profile="tag-conflicts-v1",
            existing_tags=("Harmony",),
        )


def test_empty_candidates_only_allow_keep_new() -> None:
    with pytest.raises(ValueError, match="keep_new"):
        TagConflictResolution(
            paragraph_id="p-1",
            resolutions=(("Harmony", "reuse_existing", "Harmony"),),
            resolution_profile="tag-conflicts-v1",
        )


def test_every_generated_tag_has_exactly_one_resolution() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        TagConflictResolution(
            paragraph_id="p-1",
            resolutions=(("Harmony", "keep_new", "Harmony"),),
            resolution_profile="tag-conflicts-v1",
            generated_tags=("Harmony", "Melody"),
        )


def test_empty_generation_cannot_return_conflict_resolutions() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        TagConflictResolution(
            paragraph_id="p-1",
            resolutions=(("Unexpected", "keep_new", "Unexpected"),),
            resolution_profile="tag-conflicts-v1",
            generated_tags=(),
        )


def test_conflict_resolver_is_an_async_provider_port() -> None:
    assert hasattr(TagConflictResolver, "resolve")
