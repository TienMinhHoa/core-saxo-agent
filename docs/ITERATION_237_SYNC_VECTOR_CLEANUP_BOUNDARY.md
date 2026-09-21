# Iteration 237 — bounded cleanup cho vector index synchronous

## Phạm vi

Tiếp tục thực hiện mục 12.2 và tiêu chí nghiệm thu 17 trong
`docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: mọi thao tác blocking ở boundary
async phải chạy qua bounded worker. Chọn thay đổi nhỏ nhất còn thiếu ở
composition root: vector index tùy biến chỉ cung cấp `close()` synchronous.

## Thay đổi

- `src/saxophone/app/factory.py` giữ ưu tiên `aclose()` async.
- Nhánh fallback `close()` nay chạy qua `anyio.to_thread.run_sync` với cùng
  `io_limiter` bounded của application, nên shutdown không gọi SDK blocking
  trực tiếp trên event loop.
- Thêm contract test chứng minh `close()` được chuyển qua worker và vẫn được
  gọi khi lifespan kết thúc.

## Bằng chứng kiểm tra

- Targeted: `uv run pytest tests/test_phase_1_composition_root.py -q`
- Full: `uv run pytest -q`
- Static: `uv run python -m compileall -q src app.py tests`
- Hygiene: `git diff --check`

Live model-service smoke và production parity chưa chạy được vì checkout vẫn
không có endpoint, credential và catalog production hợp lệ.
