from __future__ import annotations

import subprocess
import sys


def test_services_facade_keeps_extract_topic_implementation_lazy() -> None:
    """Importing the internal facade should not load its heavy use-case module."""

    script = """
import importlib
import sys

package = importlib.import_module("saxophone.services")
assert package.__all__ == ["ExtractTopicService"]
assert "saxophone.services.extract_topic" not in sys.modules

service = package.ExtractTopicService
assert service.__module__ == "saxophone.services.extract_topic"
assert "saxophone.services.extract_topic" in sys.modules
"""
    subprocess.run([sys.executable, "-c", script], check=True)
