# Iteration 42 — Lý do thiếu bằng chứng trong ChatResult

## Phạm vi

Phase 6 của `docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md` yêu cầu chat chuẩn
hóa error response và trả rõ policy khi evidence không đủ. Trước iteration này,
`EvidenceBundle` đã có `insufficiency_reason`, nhưng `AnswerQuestion` làm mất
giá trị đó và API chỉ trả `status`.

## Thay đổi

- Thêm `ChatResult.insufficiency_reason` và invariant: kết quả
  `insufficient_evidence` bắt buộc có lý do; kết quả `answered` không được có
  lý do thiếu nguồn.
- `AnswerQuestion` truyền nguyên nhân từ `EvidenceBundle` sang kết quả chat,
  không gọi answer generator khi không có hit.
- API `/api/v1/chat` công khai trường `insufficiency_reason`; không thêm
  reasoning nội bộ hay dữ liệu provider.
- Giữ tương thích cho kết quả `answered` bằng giá trị mặc định `None`.

## Bằng chứng kiểm thử

- `uv run pytest tests/test_chat_answer_question.py tests/test_phase_7_api_routes.py -q`
  → **28 passed**, 1 warning deprecation từ Starlette.
- Test chat use case xác minh lý do `no matching evidence` được giữ lại và
  generator không bị gọi.
- Test API xác minh response thiếu nguồn có cùng lý do và không lộ trường
  `reasoning`.

## Giới hạn còn lại

Live model-service smoke và production retrieval parity vẫn chưa thể xác minh
trong checkout này vì chưa có endpoint, credential và catalog production thật.
