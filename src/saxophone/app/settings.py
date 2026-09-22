"""Typed, validated configuration for the Saxophone backend."""

from __future__ import annotations

import math
import re
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
    remote_gpu_health_cache_seconds: float = 5.0
    remote_gpu_health_timeout_seconds: float = 5.0
    litellm_endpoint: str = ""
    litellm_model_profile: str = "saxophone-default"
    litellm_timeout_seconds: float = 30.0
    litellm_max_attempts: int = 1
    litellm_retry_backoff_seconds: float = 0.0
    litellm_retry_jitter_ratio: float = 0.0
    litellm_circuit_breaker_failure_threshold: int = 0
    litellm_circuit_breaker_cooldown_seconds: float = 30.0
    litellm_structured_output_mode: str = "json_schema"
    chunk_tagging_enabled: bool = False
    chroma_persist_directory: Path = Path("runtime/saxophone/chroma")
    chroma_collection_name: str = "saxophone_chunks"
    chroma_concept_collection_name: str = "concept_catalog"
    embedding_dimension: int = 1536
    max_upload_bytes: int = 200 * 1024 * 1024

    def __post_init__(self) -> None:
        """Keep direct construction subject to the same runtime contract."""
        _validate_runtime_path(self.data_root, "data_root")
        _validate_runtime_path(
            self.chroma_persist_directory, "chroma_persist_directory"
        )
        _validate_runtime_boolean(self.remote_gpu_tls_verify, "remote_gpu_tls_verify")
        _validate_canonical_runtime_text(
            self.remote_gpu_base_url, "SAXO_REMOTE_GPU_BASE_URL"
        )
        _validate_canonical_runtime_text(
            self.remote_gpu_bearer_token,
            "SAXO_REMOTE_GPU_BEARER_TOKEN",
        )
        _validate_canonical_runtime_text(self.litellm_endpoint, "SAXO_LITELLM_ENDPOINT")
        _validate_canonical_runtime_text(
            self.litellm_model_profile,
            "SAXO_LITELLM_MODEL_PROFILE",
        )
        _parse_structured_output_mode(self.litellm_structured_output_mode)
        _validate_runtime_boolean(self.chunk_tagging_enabled, "chunk_tagging_enabled")
        _validate_canonical_runtime_text(
            self.chroma_collection_name,
            "SAXO_CHROMA_COLLECTION_NAME",
        )
        _validate_canonical_runtime_text(
            self.chroma_concept_collection_name,
            "SAXO_CHROMA_CONCEPT_COLLECTION_NAME",
        )
        _parse_remote_gpu_base_url(self.remote_gpu_base_url)
        _parse_required_token(self.remote_gpu_bearer_token)
        _validate_optional_runtime_text(self.litellm_endpoint, "SAXO_LITELLM_ENDPOINT")
        if self.litellm_endpoint.strip():
            _parse_optional_https_url(
                self.litellm_endpoint,
                default=self.remote_gpu_base_url,
                variable="SAXO_LITELLM_ENDPOINT",
            )
        _parse_required_text(self.litellm_model_profile, "SAXO_LITELLM_MODEL_PROFILE")
        _parse_collection_name(self.chroma_collection_name, "SAXO_CHROMA_COLLECTION_NAME")
        _parse_collection_name(
            self.chroma_concept_collection_name,
            "SAXO_CHROMA_CONCEPT_COLLECTION_NAME",
        )
        if self.chroma_collection_name == self.chroma_concept_collection_name:
            raise SettingsValidationError(
                "SAXO_CHROMA_CONCEPT_COLLECTION_NAME must differ from "
                "SAXO_CHROMA_COLLECTION_NAME"
            )
        for field_name in (
            "remote_gpu_max_in_flight",
            "remote_gpu_retention_days",
            "litellm_max_attempts",
            "embedding_dimension",
            "max_upload_bytes",
        ):
            _validate_runtime_integer(
                getattr(self, field_name),
                field_name,
                strictly_positive=True,
            )
        _validate_runtime_integer(
            self.litellm_circuit_breaker_failure_threshold,
            "litellm_circuit_breaker_failure_threshold",
        )
        _validate_runtime_float(
            self.remote_gpu_health_cache_seconds,
            "remote_gpu_health_cache_seconds",
            strictly_positive=True,
        )
        _validate_runtime_float(
            self.remote_gpu_health_timeout_seconds,
            "remote_gpu_health_timeout_seconds",
            strictly_positive=True,
        )
        _validate_runtime_float(
            self.litellm_timeout_seconds,
            "litellm_timeout_seconds",
            strictly_positive=True,
        )
        _validate_runtime_float(
            self.litellm_retry_backoff_seconds,
            "litellm_retry_backoff_seconds",
        )
        _validate_runtime_float(
            self.litellm_retry_jitter_ratio,
            "litellm_retry_jitter_ratio",
            maximum=1.0,
        )
        _validate_runtime_float(
            self.litellm_circuit_breaker_cooldown_seconds,
            "litellm_circuit_breaker_cooldown_seconds",
            strictly_positive=True,
        )

    @classmethod
    def from_environment(cls, environment: Mapping[str, str]) -> "AppSettings":
        """Create settings from an explicit environment mapping.

        Passing the mapping in keeps process environment access at the
        application boundary and makes configuration tests deterministic.
        """
        _validate_environment_mapping(environment)
        data_root = _parse_data_root(
            environment.get("SAXO_DATA_ROOT", "runtime/saxophone")
        )
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
            "SAXO_CHROMA_COLLECTION_NAME",
        )
        concept_collection_name = _parse_collection_name(
            environment.get(
                "SAXO_CHROMA_CONCEPT_COLLECTION_NAME",
                "concept_catalog",
            ),
            "SAXO_CHROMA_CONCEPT_COLLECTION_NAME",
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
            litellm_retry_jitter_ratio=_parse_ratio(
                environment.get("SAXO_LITELLM_RETRY_JITTER_RATIO", "0"),
                "SAXO_LITELLM_RETRY_JITTER_RATIO",
            ),
            litellm_circuit_breaker_failure_threshold=_parse_non_negative_integer(
                environment.get("SAXO_LITELLM_CIRCUIT_BREAKER_FAILURE_THRESHOLD", "0"),
                "SAXO_LITELLM_CIRCUIT_BREAKER_FAILURE_THRESHOLD",
            ),
            litellm_circuit_breaker_cooldown_seconds=_parse_non_negative_float(
                environment.get("SAXO_LITELLM_CIRCUIT_BREAKER_COOLDOWN_SECONDS", "30"),
                "SAXO_LITELLM_CIRCUIT_BREAKER_COOLDOWN_SECONDS",
                strictly_positive=True,
            ),
            litellm_structured_output_mode=_parse_structured_output_mode(
                environment.get("SAXO_LITELLM_STRUCTURED_OUTPUT_MODE", "json_schema"),
            ),
            chunk_tagging_enabled=_parse_boolean(
                environment.get("SAXO_CHUNK_TAGGING_ENABLED", "false"),
                "SAXO_CHUNK_TAGGING_ENABLED",
            ),
            chroma_persist_directory=chroma_directory,
            chroma_collection_name=collection_name,
            chroma_concept_collection_name=concept_collection_name,
            embedding_dimension=_parse_positive_integer(
                environment.get("SAXO_EMBEDDING_DIMENSION", "1536"),
                "SAXO_EMBEDDING_DIMENSION",
            ),
            max_upload_bytes=_parse_positive_integer(
                environment.get("SAXO_MAX_UPLOAD_BYTES", str(200 * 1024 * 1024)),
                "SAXO_MAX_UPLOAD_BYTES",
            ),
        )


def _validate_environment_mapping(environment: object) -> None:
    if not isinstance(environment, Mapping):
        raise SettingsValidationError("environment must be a mapping of text values")
    for key, value in environment.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise SettingsValidationError("environment keys and values must be text")


def _parse_data_root(value: str | None) -> Path:
    if not value or not value.strip():
        raise SettingsValidationError("SAXO_DATA_ROOT must not be empty")
    path = Path(value)
    if path.drive and not path.is_absolute():
        raise SettingsValidationError("SAXO_DATA_ROOT must not be drive-relative")
    if path.root and not path.is_absolute():
        raise SettingsValidationError("SAXO_DATA_ROOT must not be root-relative")
    if ".." in path.parts:
        raise SettingsValidationError(
            "SAXO_DATA_ROOT must not traverse parent directories"
        )
    return path


def _parse_chroma_directory(value: str | None) -> Path:
    if not value or not value.strip():
        raise SettingsValidationError("SAXO_CHROMA_PERSIST_DIRECTORY must not be empty")
    path = Path(value)
    if path.drive and not path.is_absolute():
        raise SettingsValidationError(
            "SAXO_CHROMA_PERSIST_DIRECTORY must not be drive-relative"
        )
    if path.root and not path.is_absolute():
        raise SettingsValidationError(
            "SAXO_CHROMA_PERSIST_DIRECTORY must not be root-relative"
        )
    if ".." in path.parts:
        raise SettingsValidationError(
            "SAXO_CHROMA_PERSIST_DIRECTORY must not traverse parent directories",
        )
    return path


def _parse_remote_gpu_base_url(value: str | None) -> str:
    _validate_optional_runtime_text(value, "SAXO_REMOTE_GPU_BASE_URL")
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
        raise SettingsValidationError(
            "SAXO_REMOTE_GPU_BASE_URL must be an HTTPS URL without credentials, query, or fragment"
        )
    try:
        parsed.port
    except ValueError as error:
        raise SettingsValidationError(
            "SAXO_REMOTE_GPU_BASE_URL contains an invalid port"
        ) from error
    return url


def _parse_optional_https_url(value: str | None, *, default: str, variable: str) -> str:
    _validate_optional_runtime_text(value, variable)
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
    _validate_optional_runtime_text(value, "SAXO_REMOTE_GPU_BEARER_TOKEN")
    if not value or not value.strip():
        raise SettingsValidationError("SAXO_REMOTE_GPU_BEARER_TOKEN is required")
    token = value.strip()
    if any(ord(character) < 32 or ord(character) == 127 for character in token):
        raise SettingsValidationError(
            "SAXO_REMOTE_GPU_BEARER_TOKEN must not contain control characters",
        )
    return token


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
        raise SettingsValidationError(
            f"{variable} must be a positive integer"
        ) from error
    if number <= 0:
        raise SettingsValidationError(f"{variable} must be a positive integer")
    return number


def _parse_non_negative_integer(value: str | None, variable: str) -> int:
    try:
        number = int(value) if value is not None else -1
    except ValueError as error:
        raise SettingsValidationError(
            f"{variable} must be a non-negative integer"
        ) from error
    if number < 0:
        raise SettingsValidationError(f"{variable} must be a non-negative integer")
    return number


def _parse_required_text(value: str | None, variable: str) -> str:
    _validate_optional_runtime_text(value, variable)
    if not value or not value.strip():
        raise SettingsValidationError(f"{variable} must not be empty")
    return value.strip()


def _parse_structured_output_mode(value: object) -> str:
    variable = "SAXO_LITELLM_STRUCTURED_OUTPUT_MODE"
    if value not in {"json_schema", "json_object"}:
        raise SettingsValidationError(
            f"{variable} must be json_schema or json_object"
        )
    return value


def _parse_collection_name(
    value: str | None,
    variable: str = "SAXO_CHROMA_COLLECTION_NAME",
) -> str:
    _validate_optional_runtime_text(value, variable)
    if value is None or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_-]{1,61}[A-Za-z0-9]", value.strip()
    ):
        raise SettingsValidationError(
            f"{variable} must be 3-63 characters using letters, numbers, '_' or '-'",
        )
    return value.strip()


def _validate_optional_runtime_text(value: object, variable: str) -> None:
    if value is not None and not isinstance(value, str):
        raise SettingsValidationError(f"{variable} must be text")


def _validate_canonical_runtime_text(value: object, variable: str) -> None:
    _validate_optional_runtime_text(value, variable)
    if isinstance(value, str) and value != value.strip():
        raise SettingsValidationError(
            f"{variable} must not contain surrounding whitespace"
        )


def _parse_non_negative_float(
    value: str | None,
    variable: str,
    *,
    strictly_positive: bool = False,
) -> float:
    try:
        number = float(value) if value is not None else -1.0
    except ValueError as error:
        raise SettingsValidationError(
            f"{variable} must be a non-negative number"
        ) from error
    if (
        not math.isfinite(number)
        or (strictly_positive and number <= 0)
        or (not strictly_positive and number < 0)
    ):
        requirement = "positive" if strictly_positive else "non-negative"
        raise SettingsValidationError(f"{variable} must be {requirement}")
    return number


def _parse_ratio(value: str | None, variable: str) -> float:
    number = _parse_non_negative_float(value, variable)
    if number > 1:
        raise SettingsValidationError(f"{variable} must be between 0 and 1")
    return number


def _validate_runtime_float(
    value: object,
    field_name: str,
    *,
    strictly_positive: bool = False,
    maximum: float | None = None,
) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise SettingsValidationError(f"{field_name} must be a finite number")
    if (strictly_positive and value <= 0) or (not strictly_positive and value < 0):
        requirement = "positive" if strictly_positive else "non-negative"
        raise SettingsValidationError(f"{field_name} must be {requirement}")
    if maximum is not None and value > maximum:
        raise SettingsValidationError(f"{field_name} must be between 0 and {maximum:g}")


def _validate_runtime_path(value: object, field_name: str) -> None:
    if not isinstance(value, Path):
        raise SettingsValidationError(f"{field_name} must be a filesystem path")
    if str(value) != str(value).strip():
        raise SettingsValidationError(
            f"{field_name} must not contain surrounding whitespace"
        )
    if value == Path("."):
        raise SettingsValidationError(f"{field_name} must not be empty")
    if value.drive and not value.is_absolute():
        raise SettingsValidationError(f"{field_name} must not be drive-relative")
    if value.root and not value.is_absolute():
        raise SettingsValidationError(f"{field_name} must not be root-relative")
    if ".." in value.parts:
        raise SettingsValidationError(
            f"{field_name} must not traverse parent directories"
        )
    if any(ord(character) < 32 or ord(character) == 127 for character in str(value)):
        raise SettingsValidationError(
            f"{field_name} must not contain control characters"
        )
    _validate_windows_device_path_components(value, field_name)


def _validate_windows_device_path_components(value: Path, field_name: str) -> None:
    """Reject path segments that Windows resolves as device names."""
    reserved_names = {"CON", "PRN", "AUX", "NUL"}
    invalid_characters = set('<>:"|?*')
    for component in value.parts:
        if component == value.anchor:
            continue
        if component.endswith((" ", ".")):
            raise SettingsValidationError(
                f"{field_name} must not contain Windows-trimmed path components",
            )
        if any(character in invalid_characters for character in component):
            raise SettingsValidationError(
                f"{field_name} must not contain Windows-invalid path characters",
            )
        normalized = component.rstrip(" .")
        device_name = normalized.split(".", 1)[0].upper()
        if device_name in reserved_names or re.fullmatch(
            r"(?:COM|LPT)[1-9]", device_name
        ):
            raise SettingsValidationError(
                f"{field_name} must not contain Windows device name components",
            )


def _validate_runtime_boolean(value: object, field_name: str) -> None:
    if not isinstance(value, bool):
        raise SettingsValidationError(f"{field_name} must be a boolean")


def _validate_runtime_integer(
    value: object,
    field_name: str,
    *,
    strictly_positive: bool = False,
) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SettingsValidationError(f"{field_name} must be an integer")
    if (strictly_positive and value <= 0) or (not strictly_positive and value < 0):
        requirement = "positive" if strictly_positive else "non-negative"
        raise SettingsValidationError(f"{field_name} must be a {requirement} integer")
