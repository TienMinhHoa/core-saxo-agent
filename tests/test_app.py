from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


HAS_GRADIO = importlib.util.find_spec("gradio") is not None


@unittest.skipUnless(HAS_GRADIO, "Gradio has not been installed")
class GradioAppTest(unittest.TestCase):
    def test_empty_catalog_app_builds_without_exposing_source_directories(self) -> None:
        from app import create_app

        root = Path(__file__).resolve().parents[1] / "catalog-for-app-test"
        try:
            demo = create_app(root, "public")
            self.assertIsNotNone(demo)
        finally:
            catalog = root / "catalog.json"
            catalog.unlink(missing_ok=True)
            root.rmdir() if root.exists() else None


if __name__ == "__main__":
    unittest.main()
