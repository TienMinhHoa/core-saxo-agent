"""Source-faithful music-material retrieval MVP.

This package deliberately keeps retrieval/index text separate from the blocks
rendered to a learner.  It has no answer-generation dependency.
"""

from .service import MusicMaterialService
from .store import CatalogStore

__all__ = ["CatalogStore", "MusicMaterialService"]
