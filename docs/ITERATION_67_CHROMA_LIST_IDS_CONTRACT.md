# Iteration 67 — hợp đồng danh sách ID khi reconcile Chroma

## Phạm vi

Khóa hợp đồng đọc danh sách chunk hiện có trước bước reconcile của
`ChromaVectorIndex.list_chunk_ids`, theo yêu cầu fail-closed của
`SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: provider response sai shape hoặc chứa
ID không hợp lệ không được biến thành danh sách thiếu dữ liệu một cách im lặng.

## Thay đổi

- `list_chunk_ids` yêu cầu response là mapping có `ids` dạng list.
- Mọi phần tử ID phải là chuỗi không trống; response sai bị từ chối bằng
  `ValueError` thay vì lọc bỏ phần tử lỗi.
- Bổ sung regression tests cho `ids` sai kiểu, chuỗi trắng và phần tử không phải
  chuỗi.

## Bằng chứng kiểm thử

- `uv run pytest tests/test_phase_4_ingestion_contract.py -q`: **27 passed**.
- `uv run pytest -q`: **405 passed, 2 skipped, 1 warning**.
- `python -m compileall -q src tests`: thành công.
- `git diff --check`: thành công; chỉ còn cảnh báo chuyển LF sang CRLF của Git
  trên Windows.

## Giới hạn

Đây là kiểm chứng offline với adapter/fake collection. Live model-service,
production Chroma và deployment vẫn chưa được xác minh vì checkout chưa có
endpoint, credential và catalog production.
