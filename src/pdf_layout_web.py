"""Compatibility module for direct PDF layout viewer imports.

The implementation lives under the backend's ``saxophone.interfaces``
namespace; the supported web entrypoint is ``saxophone-api``. This module
remains only for direct ``python -m pdf_layout_web`` invocations.
"""

from saxophone.interfaces.pdf_layout_web import app, main

__all__ = ["app", "main"]


if __name__ == "__main__":
    main()
