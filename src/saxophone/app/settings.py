"""Typed, validated configuration for the Saxophone backend."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
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
    remote_gpu_health_cache_seconds: float = 5.0
    remote_gpu_health_timeout_seconds: float = 5.0
    litellm_endpoint: str = ""
    litellm_model_profile: str = "saxophone-default"
    litellm_timeout_seconds: float = 30.0
    litellm_max_attempts: int = 1
    litellm_retry_backoff_seconds: float = 0.0
    chroma_persist_directory: Path = Path("runtime/saxophone/chroma")
    chroma_collection_name: str = "saxophone_chunks"
    embedding_dimension: int = 1536
    max_upload_bytes: int = 200 * 1024 * 1024

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
        endpoint = _parse_optional_https_url(
            environment.get("SAXO_LITELLM_ENDPOINT"),
            default=f"{base_url.rstrip('/')}/v1/invoke",
            variable="SAXO_LITELLM_ENDPOINT",
        )
        chroma_directory = _parse_chroma_directory(
            environment.get("SAXO_CHROMA_PERSIST_DIRECTORY", str(data_root / "chroma")),
        )
        collection_name = _parse_collection_name(
            environment.get("SAXO_CHROMA_COLLECTION_NAME", "saxophone_chunks"),
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
            remote_gpu_health_cache_seconds=_parse_non_negative_float(
                environment.get("SAXO_REMOTE_GPU_HEALTH_CACHE_SECONDS", "5"),
                "SAXO_REMOTE_GPU_HEALTH_CACHE_SECONDS",
                strictly_positive=True,
            ),
            remote_gpu_health_timeout_seconds=_parse_non_negative_float(
                environment.get("SAXO_REMOTE_GPU_HEALTH_TIMEOUT_SECONDS", "5"),
                "SAXO_REMOTE_GPU_HEALTH_TIMEOUT_SECONDS",
                strictly_positive=True,
            ),
            litellm_endpoint=endpoint,
            litellm_model_profile=_parse_required_text(
                environment.get("SAXO_LITELLM_MODEL_PROFILE", "saxophone-default"),
                "SAXO_LITELLM_MODEL_PROFILE",
            ),
            litellm_timeout_seconds=_parse_non_negative_float(
                environment.get("SAXO_LITELLM_TIMEOUT_SECONDS", "30"),
                "SAXO_LITELLM_TIMEOUT_SECONDS",
                strictly_positive=True,
            ),
            litellm_max_attempts=_parse_positive_integer(
                environment.get("SAXO_LITELLM_MAX_ATTEMPTS", "1"),
                "SAXO_LITELLM_MAX_ATTEMPTS",
            ),
            litellm_retry_backoff_seconds=_parse_non_negative_float(
                environment.get("SAXO_LITELLM_RETRY_BACKOFF_SECONDS", "0"),
                "SAXO_LITELLM_RETRY_BACKOFF_SECONDS",
            ),
            chroma_persist_directory=chroma_directory,
            chroma_collection_name=collection_name,
            embedding_dimension=_parse_positive_integer(
                environment.get("SAXO_EMBEDDING_DIMENSION", "1536"),
                "SAXO_EMBEDDING_DIMENSION",
            ),
            max_upload_bytes=_parse_positive_integer(
                environment.get("SAXO_MAX_UPLOAD_BYTES", str(200 * 1024 * 1024)),
                "SAXO_MAX_UPLOAD_BYTES",
            ),
        )


def _parse_data_root(value: str | None) -> Path:
    if not value or not value.strip():
        raise SettingsValidationError("SAXO_DATA_ROOT must not be empty")
    path = Path(value.strip())
    if not path.is_absolute() and ".." in path.parts:
        raise SettingsValidationError("SAXO_DATA_ROOT must not traverse parent directories")
    return path


def _parse_chroma_directory(value: str | None) -> Path:
    if not value or not value.strip():
        raise SettingsValidationError("SAXO_CHROMA_PERSIST_DIRECTORY must not be empty")
    path = Path(value.strip())
    if not path.is_absolute() and ".." in path.parts:
        raise SettingsValidationError(
            "SAXO_CHROMA_PERSIST_DIRECTORY must not traverse parent directories",
        )
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


def _parse_optional_https_url(value: str | None, *, default: str, variable: str) -> str:
    url = default if value is None or not value.strip() else value.strip()
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise SettingsValidationError(
            f"{variable} must be an HTTPS URL without credentials, query, or fragment",
        )
    try:
        parsed.port
    except ValueError as error:
        raise SettingsValidationError(f"{variable} contains an invalid port") from error
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


def _parse_required_text(value: str | None, variable: str) -> str:
    if not value or not value.strip():
        raise SettingsValidationError(f"{variable} must not be empty")
    return value.strip()


def _parse_collection_name(value: str | None) -> str:
    if value is None or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{1,61}[A-Za-z0-9]", value.strip()):
        raise SettingsValidationError(
            "SAXO_CHROMA_COLLECTION_NAME must be 3-63 characters using letters, numbers, '_' or '-'",
        )
    return value.strip()


def _parse_non_negative_float(
    value: str | None,
    variable: str,
    *,
    strictly_positive: bool = False,
) -> float:
    try:
        number = float(value) if value is not None else -1.0
    except ValueError as error:
        raise SettingsValidationError(f"{variable} must be a non-negative number") from error
    if (strictly_positive and number <= 0) or (not strictly_positive and number < 0):
        requirement = "positive" if strictly_positive else "non-negative"
        raise SettingsValidationError(f"{variable} must be {requirement}")
    return number
