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
    assert settings.remote_gpu_base_url == "https://gpu.example.test"
    assert settings.remote_gpu_tls_verify is True
    assert settings.remote_gpu_max_in_flight == 4
    assert settings.remote_gpu_retention_days == 30
    assert settings.litellm_endpoint == "https://gpu.example.test/v1/invoke"
    assert settings.litellm_model_profile == "saxophone-default"
    assert settings.litellm_timeout_seconds == 30.0
    assert settings.litellm_max_attempts == 1
    assert settings.litellm_retry_backoff_seconds == 0.0


def test_from_environment_accepts_explicit_typed_values() -> None:
    settings = AppSettings.from_environment({
        **VALID_ENVIRONMENT,
        "SAXO_DATA_ROOT": "D:/saxo-data",
        "SAXO_REMOTE_GPU_TLS_VERIFY": "FALSE",
        "SAXO_REMOTE_GPU_MAX_IN_FLIGHT": "8",
        "SAXO_REMOTE_GPU_RETENTION_DAYS": "90",
        "SAXO_LITELLM_ENDPOINT": "https://llm.example.test/v1/chat",
        "SAXO_LITELLM_MODEL_PROFILE": "music-rag-v2",
        "SAXO_LITELLM_TIMEOUT_SECONDS": "12.5",
        "SAXO_LITELLM_MAX_ATTEMPTS": "3",
        "SAXO_LITELLM_RETRY_BACKOFF_SECONDS": "0.25",
    })

    assert settings.data_root == Path("D:/saxo-data")
    assert settings.remote_gpu_tls_verify is False
    assert settings.remote_gpu_max_in_flight == 8
    assert settings.remote_gpu_retention_days == 90
    assert settings.litellm_endpoint == "https://llm.example.test/v1/chat"
    assert settings.litellm_model_profile == "music-rag-v2"
    assert settings.litellm_timeout_seconds == 12.5
    assert settings.litellm_max_attempts == 3
    assert settings.litellm_retry_backoff_seconds == 0.25


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
    ],
)
def test_from_environment_rejects_invalid_boolean_and_positive_integer_values(
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
