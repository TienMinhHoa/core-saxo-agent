#!/usr/bin/env bash

set -Eeuo pipefail
IFS=$'\n\t'

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"

APP_HOST="${SAXO_HOST:-0.0.0.0}"
APP_PORT="${SAXO_PORT:-8000}"

die() {
    printf 'error: %s\n' "$1" >&2
    exit 1
}

on_error() {
    printf 'error: setup failed near line %s\n' "$1" >&2
}

trap 'on_error "$LINENO"' ERR

if [[ -z "$APP_HOST" ]]; then
    die "SAXO_HOST must not be blank"
fi
if [[ ! "$APP_PORT" =~ ^[0-9]+$ ]]; then
    die "SAXO_PORT must be an integer"
fi
if (( APP_PORT < 1 || APP_PORT > 65535 )); then
    die "SAXO_PORT must be between 1 and 65535"
fi

cd "$REPO_ROOT"

[[ -f "$REPO_ROOT/pyproject.toml" ]] || die "pyproject.toml is missing"
[[ -f "$REPO_ROOT/uv.lock" ]] || die "uv.lock is missing"
[[ -f "$REPO_ROOT/.env.example" ]] || die ".env.example is missing"

if [[ ! -f "$REPO_ROOT/.env" ]]; then
    cp "$REPO_ROOT/.env.example" "$REPO_ROOT/.env"
    printf 'warning: created .env from .env.example; configure credentials if required.\n' >&2
fi

if ! command -v uv >/dev/null 2>&1; then
    printf 'uv is not installed; installing it now...\n'
    if command -v curl >/dev/null 2>&1; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
    elif command -v wget >/dev/null 2>&1; then
        wget -qO- https://astral.sh/uv/install.sh | sh
    else
        die "curl or wget is required to install uv"
    fi
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
fi

command -v uv >/dev/null 2>&1 || die "uv installation completed but uv is not on PATH"

printf 'Preparing Python 3.12...\n'
uv python install 3.12

printf 'Installing locked dependencies, including the Paddle client...\n'
uv sync --locked --extra paddle-client

printf 'Starting Saxophone API on http://%s:%s\n' "$APP_HOST" "$APP_PORT"
exec uv run --locked saxophone-api --host "$APP_HOST" --port "$APP_PORT"
