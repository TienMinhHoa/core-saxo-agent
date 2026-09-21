#!/usr/bin/env python3
"""Compatibility entrypoint for the legacy music RAG UI."""

from music_rag.ui_app import create_app, main

__all__ = ["create_app", "main"]


if __name__ == "__main__":
    main()
