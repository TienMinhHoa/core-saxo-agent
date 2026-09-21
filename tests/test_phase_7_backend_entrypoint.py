from __future__ import annotations

import pytest

import saxophone.main as backend_main
from saxophone.app.settings import SettingsValidationError


REQUIRED_REMOTE_ENVIRONMENT = {
    "SAXO_REMOTE_GPU_BASE_URL": "https://explicit-gpu.example.test",
    "SAXO_REMOTE_GPU_BEARER_TOKEN": "explicit-token",
}


def _capture_application_settings(monkeypatch):
    captured: dict[str, object] = {}

    def fake_create_app(settings: object) -> object:
        captured["settings"] = settings
        return object()

    monkeypatch.setattr(backend_main, "create_app", fake_create_app)
    return captured


def _clear_remote_environment(monkeypatch) -> None:
    for name in REQUIRED_REMOTE_ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("SAXO_LAYOUT_ONLY", raising=False)


def test_create_application_loads_required_settings_from_cwd_dotenv(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    _clear_remote_environment(monkeypatch)
    (tmp_path / ".env").write_text(
        "SAXO_REMOTE_GPU_BASE_URL=https://dotenv-gpu.example.test\n"
        "SAXO_REMOTE_GPU_BEARER_TOKEN=dotenv-token\n",
        encoding="utf-8",
    )
    captured = _capture_application_settings(monkeypatch)

    backend_main.create_application()

    settings = captured["settings"]
    assert settings.remote_gpu_base_url == "https://dotenv-gpu.example.test"
    assert settings.remote_gpu_bearer_token == "dotenv-token"


def test_create_application_preserves_process_environment_over_dotenv(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "SAXO_REMOTE_GPU_BASE_URL=https://dotenv-gpu.example.test\n"
        "SAXO_REMOTE_GPU_BEARER_TOKEN=dotenv-token\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(
        "SAXO_REMOTE_GPU_BASE_URL", "https://process-gpu.example.test"
    )
    monkeypatch.setenv("SAXO_REMOTE_GPU_BEARER_TOKEN", "process-token")
    captured = _capture_application_settings(monkeypatch)

    backend_main.create_application()

    settings = captured["settings"]
    assert settings.remote_gpu_base_url == "https://process-gpu.example.test"
    assert settings.remote_gpu_bearer_token == "process-token"


def test_create_application_with_explicit_environment_does_not_load_dotenv(
    monkeypatch,
) -> None:
    def fail_if_dotenv_is_loaded(*args: object, **kwargs: object) -> None:
        raise AssertionError("explicit test environments must bypass .env loading")

    monkeypatch.setattr(backend_main, "load_dotenv", fail_if_dotenv_is_loaded)
    captured = _capture_application_settings(monkeypatch)

    backend_main.create_application(REQUIRED_REMOTE_ENVIRONMENT)

    settings = captured["settings"]
    assert settings.remote_gpu_base_url == "https://explicit-gpu.example.test"
    assert settings.remote_gpu_bearer_token == "explicit-token"


def test_create_application_reports_missing_settings_without_dotenv(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    _clear_remote_environment(monkeypatch)

    with pytest.raises(SettingsValidationError, match="SAXO_REMOTE_GPU_BASE_URL"):
        backend_main.create_application()


def test_backend_cli_delegates_to_uvicorn_factory(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_run(target: str, **kwargs: object) -> None:
        calls.append({"target": target, **kwargs})

    monkeypatch.setattr(backend_main.uvicorn, "run", fake_run)

    backend_main.main(["--host", "127.0.0.1", "--port", "8123"])

    assert calls == [
        {
            "target": "saxophone.main:create_application",
            "factory": True,
            "host": "127.0.0.1",
            "port": 8123,
        }
    ]


def test_backend_cli_help_is_local_and_does_not_start_server(monkeypatch) -> None:
    def unexpected_run(*args: object, **kwargs: object) -> None:
        raise AssertionError("--help must not start uvicorn")

    monkeypatch.setattr(backend_main.uvicorn, "run", unexpected_run)

    try:
        backend_main.main(["--help"])
    except SystemExit as error:
        assert error.code == 0
    else:
        raise AssertionError("argparse --help should exit successfully")
