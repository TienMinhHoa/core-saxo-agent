# Iteration 224 - re-check root khi đọc và xóa knowledge sidecar

## Phạm vi

Iteration này tiếp tục yêu cầu file safety trong
`docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: `JsonKnowledgeRepository` không
được tiếp tục đọc hoặc xóa qua root đã bị thay thành symbolic link sau khi
constructor hoàn tất.

## Thay đổi

- Đưa kiểm tra symbolic-link root vào `_path_for()`, là boundary dùng chung cho
  `upsert()`, `get()` và `delete()`.
- Bổ sung regression contract cho cả thao tác đọc và xóa sau khi root bị thay
  đổi; test tự skip khi Windows không có quyền tạo symbolic link.

## Bằng chứng

- Red test/contract chạy: `uv run pytest tests/test_phase_2_json_knowledge_repository.py -q --basetemp=.pytest-tmp-224-red` — **6 passed, 3 skipped**.
- Các test symbolic-link skip do Windows `WinError 1314`, không phải assertion failure.
- Chưa chạy full suite trong iteration này.
- Live model-service smoke và production parity vẫn chưa xác minh vì checkout
  thiếu endpoint, credential và production catalog.
