from __future__ import annotations

import saxophone.main as backend_main


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
