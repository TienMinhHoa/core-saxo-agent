# Iteration 235 - composition root dùng async cleanup cho Chroma

## Phạm vi

`ChromaVectorIndex` đã có `aclose()` từ iteration 234, nhưng FastAPI lifespan vẫn
gọi `close()` synchronous. Vì vậy composition root chưa thực sự dùng async
lifecycle contract khi shutdown.

## Thay đổi

- FastAPI lifespan ưu tiên `await vector_index.aclose()` nếu adapter cung cấp
  async cleanup.
- Giữ fallback `close()` cho các fake/custom vector index cũ chỉ có synchronous
  cleanup, nên compatibility của composition root vẫn được bảo toàn.
- Mở rộng regression test: Chroma vector index phải đi qua `aclose()` trong
  shutdown; test sẽ fail nếu lifecycle quay lại gọi `close()` trực tiếp.

## Bằng chứng kiểm thử

- Targeted: `1 passed, 28 deselected` với
  `uv run pytest tests/test_phase_1_composition_root.py -k
  'persistent_chroma_client_on_shutdown or closes_owned_vector_index' -q
  --basetemp=.pytest-tmp-235`.
- Trước implementation, regression test fail vì lifespan gọi `close()` trực
  tiếp; sau implementation test pass.
- Full suite: `919 passed, 18 skipped, 1 warning` với `uv run pytest -q
  --basetemp=.pytest-tmp-235`.
- `uv run python -m compileall -q src tests`: đạt.
- `git diff --check`: đạt.

## Đối chiếu kiến trúc

Thay đổi này hoàn thiện một mắt xích của yêu cầu async backend trong
`docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: lifecycle cleanup của blocking
Chroma SDK không được chạy trực tiếp trên event loop.

## Giới hạn xác minh

Live model-service smoke và production golden parity vẫn chưa thể xác minh vì
checkout hiện không có endpoint, credential và production catalog thật.
