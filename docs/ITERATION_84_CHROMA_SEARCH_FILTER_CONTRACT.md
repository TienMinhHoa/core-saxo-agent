# Iteration 84 — Hợp đồng filter cho Chroma search

## Mục tiêu

Khóa một khoảng trống trong yêu cầu `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: adapter Chroma phải kiểm tra projection/filter trước khi gọi SDK blocking. Trước iteration này, `ChromaVectorIndex.search()` chuyển nguyên trạng `filters` vào `collection.query()`.

## Thay đổi

- Bổ sung `_validated_search_filters()` tại ranh giới adapter.
- Từ chối fail-closed khi filter không phải mapping, key không phải chuỗi không-rỗng, hoặc value không phải scalar Chroma hữu hạn.
- Giữ nguyên filter scalar hợp lệ và chỉ truyền bản sao đã validate vào provider.
- Bổ sung regression tests chứng minh input lỗi không chạm provider I/O và filter hợp lệ được giữ nguyên.

## Bằng chứng kiểm chứng

```text
uv run pytest tests/test_phase_4_ingestion_contract.py -q
70 passed in 0.92s
```

Các trường hợp được kiểm tra gồm list thay cho mapping, key rỗng/không phải chuỗi, `None`, list lồng, mapping lồng và filter scalar hợp lệ.

## Phạm vi còn lại

Đây là kiểm chứng offline trên fake collection. Chưa có endpoint, credential và catalog production để chạy live model-service hoặc production parity smoke; không coi hai hạng mục đó đã hoàn tất.
