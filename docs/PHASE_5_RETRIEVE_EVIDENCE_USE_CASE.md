# Phase 5 - Use case RetrieveEvidence

## Phạm vi lát cắt

Iteration 10 triển khai application use case `RetrieveEvidence` theo lựa chọn
Clean Code trong `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`. Use case này là
boundary duy nhất biến kết quả `ChunkRetriever` thành `EvidenceBundle` để chat
có thể nhận evidence đã kiểm tra, không biết Chroma hay SDK cụ thể.

## Hành vi đã khóa bằng test

- Chuẩn hóa query bằng cách cắt khoảng trắng đầu/cuối và forward nguyên vẹn
  `filters` cùng `limit` cho port retrieval.
- Với hit hợp lệ, giữ thứ hạng và chunk refs, lấy source text từ metadata
  `document`, gom `image_refs` theo thứ tự xuất hiện và loại duplicate.
- Trả về `EvidenceBundle` rỗng với `insufficiency_reason` rõ ràng khi không có
  hit; không tạo evidence giả hoặc fallback im lặng.
- Từ chối hit thiếu source text và từ chối tập hit trộn nhiều
  `retrieval_version`, vì bundle chỉ được mang một version.

## Bằng chứng kiểm chứng

- Test lát cắt: `uv run pytest tests/test_retrieve_evidence.py
  tests/test_phase_5_retrieval_contract.py tests/test_chroma_semantic_retriever.py`
  -> **12 passed**.
- Regression toàn bộ: `uv run pytest` -> **101 passed, 2 skipped, 1 warning**.
- Hai skip là giới hạn môi trường đã biết: Gradio chưa cài và sample source
  không có trong checkout; không phải regression của lát cắt này.

## Ranh giới chưa triển khai

Lát cắt này chưa thêm selector/reranker, hydrate paragraph từ repository, hay
FastAPI route. Các phần đó cần contract riêng để không trộn trách nhiệm vào
use case hiện tại.
