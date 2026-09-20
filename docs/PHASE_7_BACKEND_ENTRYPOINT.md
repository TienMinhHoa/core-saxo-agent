# Phase 7 - Entrypoint backend FastAPI

## Mục tiêu

Đưa entrypoint backend mới vào package `saxophone`, để runtime FastAPI có một
lệnh chạy rõ ràng và không phụ thuộc vào UI Gradio legacy trong `app.py`.

## Thay đổi

- `src/saxophone/main.py` có `main(argv)` nhận `--host` và `--port`, sau đó
  gọi Uvicorn bằng factory `saxophone.main:create_application`.
- `pyproject.toml` công bố lệnh `saxophone-api`.
- README hướng dẫn chạy backend bằng `uv run saxophone-api`.
- `app.py` vẫn được giữ như legacy UI để bảo toàn feature-parity; tài liệu này
  không tuyên bố đã xoá toàn bộ compatibility path.

## Bằng chứng kiểm thử

Test `tests/test_phase_7_backend_entrypoint.py` xác minh CLI truyền đúng target,
factory mode, host và port cho Uvicorn mà không khởi động process thật.

Lệnh kiểm tra:

```text
uv run pytest -q tests/test_phase_7_backend_entrypoint.py
```

Kết quả sau khi hoàn thiện: 1 test passed.

## Giới hạn còn lại

Entrypoint này mới chứng minh wiring ở mức offline. Chưa thực hiện live smoke
với model service/Chroma và chưa xoá `app.py`/`pdf_layout_web.py`, vì đó là
quyết định migration feature-parity lớn hơn một lát cắt entrypoint.
