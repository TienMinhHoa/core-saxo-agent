"""Typed, validated configuration for the Saxophone backend."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit


class SettingsValidationError(ValueError):
    """Raised when a ``SAXO_*`` environment variable is invalid."""


@dataclass(frozen=True, slots=True)
class AppSettings:
    """The validated configuration accepted by the composition root."""

    data_root: Path
    remote_gpu_base_url: str
    remote_gpu_bearer_token: str = field(repr=False)
    remote_gpu_tls_verify: bool = True
    remote_gpu_max_in_flight: int = 4
    remote_gpu_retention_days: int = 30

    @classmethod
    def from_environment(cls, environment: Mapping[str, str]) -> "AppSettings":
        """Create settings from an explicit environment mapping.

        Passing the mapping in keeps process environment access at the
        application boundary and makes configuration tests deterministic.
        """
        data_root = _parse_data_root(environment.get("SAXO_DATA_ROOT", "runtime/saxophone"))
        base_url = _parse_remote_gpu_base_url(
            environment.get("SAXO_REMOTE_GPU_BASE_URL"),
        )
        bearer_token = _parse_required_token(
            environment.get("SAXO_REMOTE_GPU_BEARER_TOKEN"),
        )
        return cls(
            data_root=data_root,
            remote_gpu_base_url=base_url,
            remote_gpu_bearer_token=bearer_token,
            remote_gpu_tls_verify=_parse_boolean(
                environment.get("SAXO_REMOTE_GPU_TLS_VERIFY", "true"),
                "SAXO_REMOTE_GPU_TLS_VERIFY",
            ),
            remote_gpu_max_in_flight=_parse_positive_integer(
                environment.get("SAXO_REMOTE_GPU_MAX_IN_FLIGHT", "4"),
                "SAXO_REMOTE_GPU_MAX_IN_FLIGHT",
            ),
            remote_gpu_retention_days=_parse_positive_integer(
                environment.get("SAXO_REMOTE_GPU_RETENTION_DAYS", "30"),
                "SAXO_REMOTE_GPU_RETENTION_DAYS",
            ),
        )


def _parse_data_root(value: str | None) -> Path:
    if not value or not value.strip():
        raise SettingsValidationError("SAXO_DATA_ROOT must not be empty")
    path = Path(value.strip())
    if not path.is_absolute() and ".." in path.parts:
        raise SettingsValidationError("SAXO_DATA_ROOT must not traverse parent directories")
    return path


def _parse_remote_gpu_base_url(value: str | None) -> str:
    if not value or not value.strip():
        raise SettingsValidationError("SAXO_REMOTE_GPU_BASE_URL is required")
    url = value.strip()
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise SettingsValidationError("SAXO_REMOTE_GPU_BASE_URL must be an HTTPS URL without credentials, query, or fragment")
    try:
        parsed.port
    except ValueError as error:
        raise SettingsValidationError("SAXO_REMOTE_GPU_BASE_URL contains an invalid port") from error
    return url


def _parse_required_token(value: str | None) -> str:
    if not value or not value.strip():
        raise SettingsValidationError("SAXO_REMOTE_GPU_BEARER_TOKEN is required")
    return value.strip()


def _parse_boolean(value: str | None, variable: str) -> bool:
    if value is not None and value.strip().lower() == "true":
        return True
    if value is not None and value.strip().lower() == "false":
        return False
    raise SettingsValidationError(f"{variable} must be true or false")


def _parse_positive_integer(value: str | None, variable: str) -> int:
    try:
        number = int(value) if value is not None else 0
    except ValueError as error:
        raise SettingsValidationError(f"{variable} must be a positive integer") from error
    if number <= 0:
        raise SettingsValidationError(f"{variable} must be a positive integer")
    return number
