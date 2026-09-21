"""Compatibility entrypoint for the legacy PDF layout viewer.

The implementation lives under the backend's ``saxophone.interfaces``
namespace; this module remains only for the historical console script and
direct ``python -m pdf_layout_web`` invocations.
"""

from saxophone.interfaces.pdf_layout_web import app, main

__all__ = ["app", "main"]


if __name__ == "__main__":
    main()
