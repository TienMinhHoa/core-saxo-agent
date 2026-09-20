# Phase 7 — API retrieval/chat và bằng chứng xác minh

## Phạm vi lát cắt

Iteration này chọn hướng Clean Code: thêm inbound adapter FastAPI mỏng cho hai
capability đã có use case (`RetrieveEvidence` và `AnswerQuestion`). Route không
biết Chroma, HTTP model transport hay GPU; dependency chỉ đi vào qua
`AppOverrides` và `AppContainer`.

## Thay đổi đã thực hiện

- Thêm `saxophone.interfaces.api` với request schema có giới hạn `limit`,
  normalize chuỗi đầu vào và response projection typed cho evidence/chat.
- Thêm `POST /api/v1/retrieval/evidence` và `POST /api/v1/chat`.
- Khi capability chưa được compose, route trả `503` rõ ràng thay vì tạo provider
  ngầm hoặc fallback dữ liệu giả.
- Health endpoint phản ánh `retrieval`/`chat` là `ready` khi use case được inject;
  extraction/ingestion vẫn `disabled` vì chưa có application use case tương ứng.
- Response chat chỉ chứa answer, citations, usage và cost; không expose reasoning
  nội bộ.

## Bằng chứng kiểm tra

Đã chạy offline trong checkout này:

```text
uv run pytest tests/test_phase_7_api_routes.py tests/test_phase_1_composition_root.py
10 passed, 1 warning

python -m compileall -q src tests
pass
```

Contract tests bao phủ: projection evidence thiếu kết quả, normalize query và
forward `limit`; chat thiếu evidence an toàn; và capability chưa compose trả 503.

## Trạng thái so với kiến trúc đích

Lát cắt này hoàn thành inbound API boundary cho retrieval/chat, nhưng chưa chứng
minh end-to-end upload → extraction → ingestion → search → chat. Extraction và
ingestion vẫn cần use case/adapter và composition tiếp theo; chưa chạy live
model-service hoặc Chroma thật.
