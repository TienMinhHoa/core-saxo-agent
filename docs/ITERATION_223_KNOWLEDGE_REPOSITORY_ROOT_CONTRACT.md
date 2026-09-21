# Iteration 223 - siết root của knowledge repository

## Phạm vi

Iteration này hoàn tất một slice nhỏ của yêu cầu file safety trong
`docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: `JsonKnowledgeRepository` phải
fail-closed khi nhận root không phải `Path`, root hiện hữu nhưng là file, hoặc
root đi qua symbolic link. Root chưa tồn tại vẫn được phép để repository tạo
sidecar khi ghi lần đầu.

## Thay đổi

- Kiểm tra kiểu runtime của `root` tại constructor.
- Từ chối root hiện hữu không phải thư mục.
- Từ chối symbolic link ở root hoặc trên các path component của root trước khi
  `resolve()`; kiểm tra lại trước khi tạo thư mục trong worker ghi.
- Bổ sung contract tests cho ba trường hợp biên; test symbolic link tự skip khi
  Windows checkout không có quyền tạo link.

## Bằng chứng

- `uv run pytest tests/test_phase_2_json_knowledge_repository.py -q --basetemp=.pytest-tmp-223`:
  **6 passed, 1 skipped**.
- `uv run pytest -q --basetemp=.pytest-tmp-223-full`:
  **911 passed, 4 skipped, 1 warning**.
- Skip symbolic link là do Windows `WinError 1314` thiếu privilege, không phải
  test failure.
- Chưa chạy live model-service smoke/production parity vì checkout vẫn thiếu
  endpoint, credential và production catalog thật.
