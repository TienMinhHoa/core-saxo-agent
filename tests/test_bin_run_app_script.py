from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "bin" / "run_app.sh"


def test_run_app_script_bootstraps_locked_environment_and_starts_api() -> None:
    content = SCRIPT.read_text(encoding="utf-8")

    assert content.startswith("#!/usr/bin/env bash\n")
    assert "set -Eeuo pipefail" in content
    assert 'BASH_SOURCE[0]' in content
    assert 'cd "$REPO_ROOT"' in content
    assert 'APP_HOST="${SAXO_HOST:-0.0.0.0}"' in content
    assert 'APP_PORT="${SAXO_PORT:-8000}"' in content
    assert "https://astral.sh/uv/install.sh" in content
    assert "uv python install 3.12" in content
    assert "uv sync --locked --extra paddle-client" in content
    assert 'exec uv run --locked saxophone-api --host "$APP_HOST" --port "$APP_PORT"' in content


def test_run_app_script_prepares_dotenv_and_validates_bind_settings() -> None:
    content = SCRIPT.read_text(encoding="utf-8")

    assert 'cp "$REPO_ROOT/.env.example" "$REPO_ROOT/.env"' in content
    assert '[[ -z "$APP_HOST" ]]' in content
    assert '[[ ! "$APP_PORT" =~ ^[0-9]+$ ]]' in content
    assert "APP_PORT < 1 || APP_PORT > 65535" in content
