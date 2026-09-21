# Iteration 256 - runbook Phase 7

## Mục tiêu

Đóng mục còn thiếu của Phase 7: cập nhật README/runbook để người vận hành
biết cách chạy backend CPU-only, cấu hình model service và phân biệt kiểm tra
offline với live smoke.

## Thay đổi

- Thêm `README.md` với lệnh `uv sync --locked`, entrypoint duy nhất
  `saxophone-api`, các biến môi trường quan trọng và lệnh kiểm tra.
- Ghi rõ backend không chứa CUDA/Paddle/model weights cục bộ và không dùng job
  lifecycle cho model request.
- Ghi rõ token là secret, artifact phải truyền qua URI/upload có kiểm soát và
  live smoke không được suy ra từ test offline.

## Bằng chứng

- `pyproject.toml` khai báo `readme = "README.md"`, script
  `saxophone-api = "saxophone.main:main"` và Python `>=3.12,<3.13`.
- `src/saxophone/main.py` tạo app qua `create_application` và chạy đúng một
  ASGI entrypoint.
- `tests/test_phase_7_dependency_enforcement.py` đã kiểm tra dependency
  boundary, GPU runtime, transport boundary và tách runtime/dev dependency.

## Xác minh iteration

Chạy sau khi cập nhật:

```powershell
uv run pytest
uv run python -m compileall src tests
git diff --check
```

Live model-service smoke và production parity vẫn **chưa xác minh** vì
checkout không có endpoint, credential và production catalog thật.
