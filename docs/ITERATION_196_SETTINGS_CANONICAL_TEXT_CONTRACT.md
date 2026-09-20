# Iteration 196 — hợp đồng text canonical cho `AppSettings`

## Phạm vi

Khóa một khoảng hở giữa hai đường tạo cấu hình: `from_environment()` đã
`strip()` giá trị text, nhưng khởi tạo `AppSettings` trực tiếp chỉ kiểm tra
bản đã strip mà vẫn giữ giá trị có khoảng trắng ở đầu/cuối.

## Thay đổi

- Bổ sung kiểm tra runtime cho text canonical tại `AppSettings.__post_init__`.
- Từ chối surrounding whitespace ở URL GPU, bearer token, LiteLLM endpoint,
  model profile và tên Chroma collection.
- Giữ nguyên hành vi hợp lệ của parser environment; giá trị từ environment
  tiếp tục được chuẩn hóa trước khi tạo settings.
- Bổ sung 5 regression tests theo TDD trong
  `tests/test_phase_1_settings.py`.

## Bằng chứng

- Targeted: `uv run pytest -q tests/test_phase_1_settings.py -k
  "canonical_text or settings_construction_rejects_non_canonical_text"` →
  **5 passed**.
- Full offline suite: `uv run pytest -q` → **808 passed, 3 skipped, 1
  warning**.
- Skip hiện hữu: Gradio không cài, sample source không có, Windows không có
  quyền tạo symbolic link.
- Live model-service smoke và production golden parity vẫn chưa xác minh vì
  checkout chưa có endpoint, credential và catalog production thật.
