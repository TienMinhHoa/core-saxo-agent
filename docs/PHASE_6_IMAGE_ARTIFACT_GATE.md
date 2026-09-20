# Phase 6 - Image artifact gate

## Phạm vi iteration

Đã thêm cổng `ImageArtifactGate` giữa `RetrieveEvidence` và `AnswerGenerator`.
Chat không chuyển image reference thô cho provider: nếu evidence có ảnh thì phải
cấu hình gate; `SafeImageArtifactGate` chỉ chấp nhận reference tương đối thuộc
backend, từ chối đường dẫn tuyệt đối, URI remote và path traversal.

## Bằng chứng

- Test mới kiểm tra: thiếu gate bị từ chối, reference hợp lệ được chuyển qua,
  và path tuyệt đối/remote bị từ chối.
- Validation offline: targeted `uv run pytest tests/test_chat_answer_question.py` đạt
  `6 passed`; full `uv run pytest` đạt `111 passed, 2 skipped, 1 warning`.
- `python -m compileall -q src tests` và `git diff --check` đều đạt.

## Ranh giới còn lại

Gate hiện có hai lớp kiểm tra: `SafeImageArtifactGate` kiểm tra hình dạng
reference; `RepositoryBackedImageArtifactGate` resolve reference thành
`ArtifactRef`, bắt buộc `ArtifactKind.IMAGE`, đọc bytes qua
`ArtifactRepository`, rồi kiểm tra lại kích thước và SHA-256 trước khi cho
provider nhận evidence. Resolver vẫn là port/đối tượng inject được, nên chat
không phụ thuộc filesystem hay registry cụ thể.

Contract test tại `tests/test_phase_6_image_artifact_repository_gate.py` chứng
minh round-trip hợp lệ, từ chối artifact không phải ảnh và phát hiện payload
bị sửa sau khi lưu.
