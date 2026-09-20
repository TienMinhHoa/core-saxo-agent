# Hợp đồng query của legacy retrieval adapter

## Phạm vi iteration 5

`LegacySemanticRetriever` là compatibility adapter nhưng vẫn phải tuân thủ cùng
quy tắc input cơ bản với các retriever mới: query phải là chuỗi có nội dung.
Adapter trim khoảng trắng trước khi gọi `semantic_search`, và từ chối query rỗng
ở boundary bằng `ValueError` thay vì để lỗi trôi xuống legacy catalog.

## Bằng chứng

- Test hồi quy: `tests/test_hybrid_retrieval.py::test_legacy_semantic_retriever_rejects_blank_query_at_port_boundary`.
- Test kiểm tra query chỉ gồm whitespace với `access_scope` hợp lệ.
- Test xác nhận lỗi xảy ra tại port boundary, không cần mở catalog hay gọi embedding provider.

## Trạng thái kiểm chứng

Đã chạy targeted test và full offline suite sau khi thay đổi. Đây là kiểm chứng
offline; golden parity production và live model-service smoke vẫn cần catalog
fixture được chấp thuận cùng endpoint/credential thật.
