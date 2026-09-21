# Iteration 241 — Chroma factory không che mất lỗi khởi tạo

## Phạm vi

Khóa contract fail-closed của `create_chroma_vector_index()`: khi tạo
`ChromaVectorIndex` thất bại, factory vẫn phải cố gắng đóng `PersistentClient`;
nếu thao tác đóng cũng phát sinh `Exception`, lỗi khởi tạo ban đầu vẫn là lỗi
được trả về cho caller.

## Thay đổi

- Bổ sung regression test
  `test_chroma_client_cleanup_error_does_not_mask_factory_failure`.
- Test mô phỏng constructor của vector index ném `ValueError` và
  `client.close()` ném lỗi khác; kết quả vẫn giữ nguyên `ValueError` ban đầu.
- Không thay đổi runtime code vì implementation hiện tại đã dùng
  `suppress(Exception)` đúng với contract này.

## Bằng chứng kiểm thử

Lệnh:

```text
uv run pytest tests/test_phase_1_composition_root.py -k "chroma_client_cleanup_error_does_not_mask_factory_failure or chroma_client_is_closed_when_vector_index_construction_fails" --basetemp=.pytest-tmp
```

Kết quả: **2 passed, 33 deselected, 1 warning**.

## Trạng thái còn lại

Iteration này chỉ khóa behavior offline ở factory boundary. Live model-service
smoke và production golden parity vẫn chưa xác minh vì checkout chưa có
endpoint, credential và production catalog thật.
