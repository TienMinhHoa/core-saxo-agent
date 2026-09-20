# Iteration 50 — kiểm chứng image artifact gate trong chat

## Phạm vi

Tách một lỗi trong test contract của Phase 6: hai test image-gating trước đây
khởi tạo `ImageRetriever([])`. Vì không có hit, `RetrieveEvidence` trả về
insufficiency ngay và `AnswerQuestion` không bao giờ đi qua nhánh kiểm tra hoặc
gọi `ImageArtifactGate`.

## Thay đổi

- Cập nhật test từ no-hit fixture sang hit có `metadata.image_refs` thật.
- Test unsafe reference `../secret.png` phải bị `SafeImageArtifactGate` từ chối
  trước khi gọi answer generator.
- Test reference tương đối an toàn `images/page-1.png` phải được gate rồi mới
  truyền vào evidence của answer generator.

## Bằng chứng kiểm thử

- `uv run pytest tests/test_chat_answer_question.py -q`: **12 passed**.
- `uv run pytest -q`: **344 passed, 2 skipped, 1 warning**.
- `python -m compileall -q src tests`: đạt.
- `git diff --check`: đạt.

## Trạng thái và giới hạn

Slice này hoàn tất exit criterion image refs phải qua artifact gate ở chat
boundary bằng contract test có dữ liệu chạy thật. Live model-service smoke và
production legacy parity vẫn chưa thể xác minh vì checkout hiện không có
endpoint, credential và catalog production được phê duyệt.
