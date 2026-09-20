from __future__ import annotations

from pathlib import Path

import pytest

from saxophone.app.settings import AppSettings, SettingsValidationError


VALID_ENVIRONMENT = {
    "SAXO_REMOTE_GPU_BASE_URL": "https://gpu.example.test",
    "SAXO_REMOTE_GPU_BEARER_TOKEN": "test-token-must-not-leak",
}


def test_from_environment_uses_safe_defaults() -> None:
    settings = AppSettings.from_environment(VALID_ENVIRONMENT)

    assert settings.data_root == Path("runtime/saxophone")
    assert settings.max_upload_bytes == 200 * 1024 * 1024
    assert settings.remote_gpu_base_url == "https://gpu.example.test"
    assert settings.remote_gpu_tls_verify is True
    assert settings.remote_gpu_max_in_flight == 4
    assert settings.remote_gpu_retention_days == 30
    assert settings.remote_gpu_health_cache_seconds == 5.0
    assert settings.remote_gpu_health_timeout_seconds == 5.0
    assert settings.litellm_endpoint == "https://gpu.example.test/v1/invoke"
    assert settings.litellm_model_profile == "saxophone-default"
    assert settings.litellm_timeout_seconds == 30.0
    assert settings.litellm_max_attempts == 1
    assert settings.litellm_retry_backoff_seconds == 0.0
    assert settings.litellm_retry_jitter_ratio == 0.0
    assert settings.litellm_circuit_breaker_failure_threshold == 0
    assert settings.litellm_circuit_breaker_cooldown_seconds == 30.0
    assert settings.chroma_persist_directory == Path("runtime/saxophone/chroma")
    assert settings.chroma_collection_name == "saxophone_chunks"
    assert settings.embedding_dimension == 1536


def test_from_environment_accepts_explicit_typed_values() -> None:
    settings = AppSettings.from_environment({
        **VALID_ENVIRONMENT,
        "SAXO_DATA_ROOT": "D:/saxo-data",
        "SAXO_REMOTE_GPU_TLS_VERIFY": "FALSE",
        "SAXO_REMOTE_GPU_MAX_IN_FLIGHT": "8",
        "SAXO_REMOTE_GPU_RETENTION_DAYS": "90",
        "SAXO_REMOTE_GPU_HEALTH_CACHE_SECONDS": "7.5",
        "SAXO_REMOTE_GPU_HEALTH_TIMEOUT_SECONDS": "2.5",
        "SAXO_LITELLM_ENDPOINT": "https://llm.example.test/v1/chat",
        "SAXO_LITELLM_MODEL_PROFILE": "music-rag-v2",
        "SAXO_LITELLM_TIMEOUT_SECONDS": "12.5",
        "SAXO_LITELLM_MAX_ATTEMPTS": "3",
        "SAXO_LITELLM_RETRY_BACKOFF_SECONDS": "0.25",
        "SAXO_LITELLM_RETRY_JITTER_RATIO": "0.2",
        "SAXO_LITELLM_CIRCUIT_BREAKER_FAILURE_THRESHOLD": "5",
        "SAXO_LITELLM_CIRCUIT_BREAKER_COOLDOWN_SECONDS": "45.5",
        "SAXO_CHROMA_PERSIST_DIRECTORY": "D:/saxo-data/chroma",
        "SAXO_CHROMA_COLLECTION_NAME": "music_chunks_v2",
        "SAXO_EMBEDDING_DIMENSION": "1024",
        "SAXO_MAX_UPLOAD_BYTES": "4096",
    })

    assert settings.data_root == Path("D:/saxo-data")
    assert settings.remote_gpu_tls_verify is False
    assert settings.remote_gpu_max_in_flight == 8
    assert settings.remote_gpu_retention_days == 90
    assert settings.remote_gpu_health_cache_seconds == 7.5
    assert settings.remote_gpu_health_timeout_seconds == 2.5
    assert settings.litellm_endpoint == "https://llm.example.test/v1/chat"
    assert settings.litellm_model_profile == "music-rag-v2"
    assert settings.litellm_timeout_seconds == 12.5
    assert settings.litellm_max_attempts == 3
    assert settings.litellm_retry_backoff_seconds == 0.25
    assert settings.litellm_retry_jitter_ratio == 0.2
    assert settings.litellm_circuit_breaker_failure_threshold == 5
    assert settings.litellm_circuit_breaker_cooldown_seconds == 45.5
    assert settings.chroma_persist_directory == Path("D:/saxo-data/chroma")
    assert settings.chroma_collection_name == "music_chunks_v2"
    assert settings.embedding_dimension == 1024
    assert settings.max_upload_bytes == 4096


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("SAXO_CHROMA_PERSIST_DIRECTORY", ""),
        ("SAXO_CHROMA_PERSIST_DIRECTORY", "../outside"),
        ("SAXO_CHROMA_COLLECTION_NAME", ""),
        ("SAXO_CHROMA_COLLECTION_NAME", "bad name"),
        ("SAXO_EMBEDDING_DIMENSION", "0"),
        ("SAXO_EMBEDDING_DIMENSION", "-1"),
        ("SAXO_EMBEDDING_DIMENSION", "not-an-integer"),
        ("SAXO_MAX_UPLOAD_BYTES", "0"),
        ("SAXO_MAX_UPLOAD_BYTES", "-1"),
        ("SAXO_MAX_UPLOAD_BYTES", "not-an-integer"),
    ],
)
def test_from_environment_rejects_invalid_chroma_and_embedding_configuration(
    variable: str,
    value: str,
) -> None:
    with pytest.raises(SettingsValidationError) as error:
        AppSettings.from_environment({**VALID_ENVIRONMENT, variable: value})

    assert variable in str(error.value)


@pytest.mark.parametrize(
    "missing_variable",
    ["SAXO_REMOTE_GPU_BASE_URL", "SAXO_REMOTE_GPU_BEARER_TOKEN"],
)
def test_from_environment_rejects_missing_required_remote_gpu_configuration(
    missing_variable: str,
) -> None:
    environment = {key: value for key, value in VALID_ENVIRONMENT.items() if key != missing_variable}

    with pytest.raises(SettingsValidationError) as error:
        AppSettings.from_environment(environment)

    assert missing_variable in str(error.value)
    assert VALID_ENVIRONMENT["SAXO_REMOTE_GPU_BEARER_TOKEN"] not in str(error.value)


@pytest.mark.parametrize(
    "base_url",
    [
        "http://gpu.example.test",
        "/relative-gpu",
        "https://token@gpu.example.test",
        "https://gpu.example.test?trace=true",
        "https://gpu.example.test#fragment",
    ],
)
def test_from_environment_rejects_unsafe_remote_gpu_url(base_url: str) -> None:
    with pytest.raises(SettingsValidationError) as error:
        AppSettings.from_environment({**VALID_ENVIRONMENT, "SAXO_REMOTE_GPU_BASE_URL": base_url})

    assert "SAXO_REMOTE_GPU_BASE_URL" in str(error.value)


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("SAXO_REMOTE_GPU_TLS_VERIFY", "yes"),
        ("SAXO_REMOTE_GPU_MAX_IN_FLIGHT", "zero"),
        ("SAXO_REMOTE_GPU_MAX_IN_FLIGHT", "0"),
        ("SAXO_REMOTE_GPU_MAX_IN_FLIGHT", "-1"),
        ("SAXO_REMOTE_GPU_RETENTION_DAYS", "0"),
        ("SAXO_REMOTE_GPU_RETENTION_DAYS", "-30"),
        ("SAXO_REMOTE_GPU_HEALTH_TIMEOUT_SECONDS", "0"),
        ("SAXO_REMOTE_GPU_HEALTH_TIMEOUT_SECONDS", "-1"),
    ],
)
def test_from_environment_rejects_invalid_boolean_and_positive_integer_values(
    variable: str,
    value: str,
) -> None:
    with pytest.raises(SettingsValidationError) as error:
        AppSettings.from_environment({**VALID_ENVIRONMENT, variable: value})

    assert variable in str(error.value)


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("SAXO_LITELLM_RETRY_JITTER_RATIO", "-0.1"),
        ("SAXO_LITELLM_RETRY_JITTER_RATIO", "1.1"),
        ("SAXO_LITELLM_CIRCUIT_BREAKER_FAILURE_THRESHOLD", "-1"),
        ("SAXO_LITELLM_CIRCUIT_BREAKER_COOLDOWN_SECONDS", "0"),
        ("SAXO_REMOTE_GPU_HEALTH_CACHE_SECONDS", "nan"),
        ("SAXO_REMOTE_GPU_HEALTH_TIMEOUT_SECONDS", "inf"),
        ("SAXO_LITELLM_TIMEOUT_SECONDS", "-inf"),
        ("SAXO_LITELLM_RETRY_BACKOFF_SECONDS", "1e999"),
    ],
)
def test_from_environment_rejects_invalid_model_retry_configuration(
    variable: str,
    value: str,
) -> None:
    with pytest.raises(SettingsValidationError) as error:
        AppSettings.from_environment({**VALID_ENVIRONMENT, variable: value})

    assert variable in str(error.value)


def test_settings_representation_and_validation_errors_never_leak_bearer_token() -> None:
    settings = AppSettings.from_environment(VALID_ENVIRONMENT)

    assert VALID_ENVIRONMENT["SAXO_REMOTE_GPU_BEARER_TOKEN"] not in repr(settings)

    with pytest.raises(SettingsValidationError) as error:
        AppSettings.from_environment({
            **VALID_ENVIRONMENT,
            "SAXO_REMOTE_GPU_BASE_URL": "http://gpu.example.test",
        })

    assert VALID_ENVIRONMENT["SAXO_REMOTE_GPU_BEARER_TOKEN"] not in str(error.value)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("remote_gpu_health_cache_seconds", float("nan")),
        ("remote_gpu_health_timeout_seconds", float("inf")),
        ("litellm_timeout_seconds", float("-inf")),
        ("litellm_retry_backoff_seconds", float("nan")),
        ("litellm_retry_jitter_ratio", 1.5),
        ("litellm_circuit_breaker_cooldown_seconds", 0.0),
    ],
)
def test_direct_settings_construction_rejects_invalid_float_contracts(
    field_name: str,
    value: float,
) -> None:
    with pytest.raises(SettingsValidationError) as error:
        AppSettings(
            data_root=Path("runtime/saxophone"),
            remote_gpu_base_url="https://gpu.example.test",
            remote_gpu_bearer_token="secret",
            **{field_name: value},
        )

    assert field_name in str(error.value)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("remote_gpu_max_in_flight", 0),
        ("remote_gpu_retention_days", -1),
        ("litellm_max_attempts", 1.0),
        ("litellm_circuit_breaker_failure_threshold", True),
        ("embedding_dimension", "1536"),
        ("max_upload_bytes", -1),
    ],
)
def test_direct_settings_construction_rejects_invalid_integer_contracts(
    field_name: str,
    value: object,
) -> None:
    with pytest.raises(SettingsValidationError) as error:
        AppSettings(
            data_root=Path("runtime/saxophone"),
            remote_gpu_base_url="https://gpu.example.test",
            remote_gpu_bearer_token="secret",
            **{field_name: value},
        )

    assert field_name in str(error.value)


@pytest.mark.parametrize(
    ("field_name", "value", "error_marker"),
    [
        ("remote_gpu_base_url", "http://gpu.example.test", "SAXO_REMOTE_GPU_BASE_URL"),
        ("remote_gpu_base_url", "https://token@gpu.example.test", "SAXO_REMOTE_GPU_BASE_URL"),
        ("remote_gpu_base_url", "https://gpu.example.test?trace=true", "SAXO_REMOTE_GPU_BASE_URL"),
        ("remote_gpu_bearer_token", "   ", "SAXO_REMOTE_GPU_BEARER_TOKEN"),
        ("remote_gpu_bearer_token", "token\nforged-header: yes", "SAXO_REMOTE_GPU_BEARER_TOKEN"),
        ("litellm_endpoint", "http://llm.example.test/v1/invoke", "SAXO_LITELLM_ENDPOINT"),
        ("litellm_model_profile", "   ", "SAXO_LITELLM_MODEL_PROFILE"),
        ("chroma_collection_name", "bad name", "SAXO_CHROMA_COLLECTION_NAME"),
    ],
)
def test_direct_settings_construction_rejects_invalid_textual_contracts(
    field_name: str,
    value: str,
    error_marker: str,
) -> None:
    values = {
        "data_root": Path("runtime/saxophone"),
        "remote_gpu_base_url": "https://gpu.example.test",
        "remote_gpu_bearer_token": "secret",
    }
    values[field_name] = value
    with pytest.raises(SettingsValidationError) as error:
        AppSettings(**values)

    assert error_marker in str(error.value)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("data_root", "runtime/saxophone"),
        ("chroma_persist_directory", "runtime/saxophone/chroma"),
        ("remote_gpu_tls_verify", "true"),
    ],
)
def test_direct_settings_construction_rejects_invalid_runtime_types(
    field_name: str,
    value: object,
) -> None:
    values = {
        "data_root": Path("runtime/saxophone"),
        "remote_gpu_base_url": "https://gpu.example.test",
        "remote_gpu_bearer_token": "secret",
    }
    values[field_name] = value

    with pytest.raises(SettingsValidationError) as error:
        AppSettings(**values)

    assert field_name in str(error.value)


@pytest.mark.parametrize(
    "field_name",
    ["data_root", "chroma_persist_directory"],
)
def test_direct_settings_construction_rejects_relative_parent_traversal(
    field_name: str,
) -> None:
    values = {
        "data_root": Path("runtime/saxophone"),
        "remote_gpu_base_url": "https://gpu.example.test",
        "remote_gpu_bearer_token": "secret",
    }
    values[field_name] = Path("../outside")

    with pytest.raises(SettingsValidationError) as error:
        AppSettings(**values)

    assert field_name in str(error.value)


@pytest.mark.parametrize(
    ("field_name", "value", "error_marker"),
    [
        ("remote_gpu_base_url", 123, "SAXO_REMOTE_GPU_BASE_URL"),
        ("remote_gpu_bearer_token", 123, "SAXO_REMOTE_GPU_BEARER_TOKEN"),
        ("litellm_endpoint", 123, "SAXO_LITELLM_ENDPOINT"),
        ("litellm_model_profile", 123, "SAXO_LITELLM_MODEL_PROFILE"),
        ("chroma_collection_name", 123, "SAXO_CHROMA_COLLECTION_NAME"),
    ],
)
def test_direct_settings_construction_rejects_invalid_text_runtime_types(
    field_name: str,
    value: object,
    error_marker: str,
) -> None:
    values = {
        "data_root": Path("runtime/saxophone"),
        "remote_gpu_base_url": "https://gpu.example.test",
        "remote_gpu_bearer_token": "secret",
    }
    values[field_name] = value

    with pytest.raises(SettingsValidationError) as error:
        AppSettings(**values)

    assert error_marker in str(error.value)


@pytest.mark.parametrize(
    "environment",
    [
        {**VALID_ENVIRONMENT, "SAXO_DATA_ROOT": Path("runtime/saxophone")},
        {**VALID_ENVIRONMENT, "SAXO_REMOTE_GPU_BASE_URL": 123},
        {**VALID_ENVIRONMENT, "SAXO_REMOTE_GPU_TLS_VERIFY": True},
        {**VALID_ENVIRONMENT, "SAXO_LITELLM_TIMEOUT_SECONDS": 30},
        {**VALID_ENVIRONMENT, "SAXO_CHROMA_COLLECTION_NAME": None},
    ],
)
def test_from_environment_rejects_non_text_environment_entries(
    environment: dict[str, object],
) -> None:
    with pytest.raises(SettingsValidationError) as error:
        AppSettings.from_environment(environment)  # type: ignore[arg-type]

    assert "environment" in str(error.value)
