"""ASGI entrypoint helpers for the Saxophone backend."""

from __future__ import annotations

from collections.abc import Mapping
import os

from fastapi import FastAPI

from saxophone.app.factory import create_app
from saxophone.app.settings import AppSettings


def create_application(environment: Mapping[str, str] | None = None) -> FastAPI:
    """Build an application at the process boundary, where environment is allowed."""

    resolved_environment = os.environ if environment is None else environment
    return create_app(AppSettings.from_environment(resolved_environment))
