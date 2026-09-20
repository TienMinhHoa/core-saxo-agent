"""ASGI entrypoint helpers for the Saxophone backend."""

from __future__ import annotations

from collections.abc import Mapping
import argparse
import os

from fastapi import FastAPI
import uvicorn

from saxophone.app.factory import create_app
from saxophone.app.settings import AppSettings


def create_application(environment: Mapping[str, str] | None = None) -> FastAPI:
    """Build an application at the process boundary, where environment is allowed."""

    resolved_environment = os.environ if environment is None else environment
    return create_app(AppSettings.from_environment(resolved_environment))


def main(argv: list[str] | None = None) -> None:
    """Run the single backend ASGI entrypoint."""

    parser = argparse.ArgumentParser(description="Run the Saxophone RAG backend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    uvicorn.run(
        "saxophone.main:create_application",
        factory=True,
        host=args.host,
        port=args.port,
    )
