"""ASGI entrypoint helpers for the Saxophone backend."""

from __future__ import annotations

from collections.abc import Mapping
import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI


class _UvicornProxy:
    """Resolve uvicorn only when the server is actually started."""

    def run(self, target: str, **kwargs: object) -> None:
        import uvicorn

        uvicorn.run(target, **kwargs)


uvicorn = _UvicornProxy()

from saxophone.app.factory import create_app, create_layout_app
from saxophone.app.settings import AppSettings


def create_application(environment: Mapping[str, str] | None = None) -> FastAPI:
    """Build an application at the process boundary, where environment is allowed."""

    if environment is None:
        load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)
        resolved_environment = os.environ
    else:
        resolved_environment = environment
    if resolved_environment.get("SAXO_LAYOUT_ONLY", "").strip().lower() == "true":
        return create_layout_app()
    return create_app(AppSettings.from_environment(resolved_environment))


def main(argv: list[str] | None = None) -> None:
    """Run the single backend ASGI entrypoint."""

    parser = argparse.ArgumentParser(description="Run the Saxophone RAG backend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--layout-only",
        action="store_true",
        help="Run PDF layout routes without requiring the general AI service",
    )
    args = parser.parse_args(argv)
    if args.layout_only:
        os.environ["SAXO_LAYOUT_ONLY"] = "true"
    uvicorn.run(
        "saxophone.main:create_application",
        factory=True,
        host=args.host,
        port=args.port,
    )
