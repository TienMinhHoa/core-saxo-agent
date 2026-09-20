# Iteration 121 — Chặn symbolic link trong đường dẫn cha của artifact

## Phạm vi

Tiếp tục contract `ArtifactRepository` của Phase 2 trong
`docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`. Iteration 120 đã chặn symbolic
link tại chính file artifact; iteration này khóa thêm các thư mục cha trong
đường dẫn `artifact_id/version`.

## Thay đổi

- `LocalArtifactRepository._path_for()` duyệt từng component tương đối dưới
  artifact root.
- Nếu bất kỳ component nào là symbolic link, repository fail-closed bằng
  `FileExistsError` trước khi tạo thư mục hoặc ghi filesystem.
- Giữ nguyên kiểm tra path đã resolve phải nằm trong artifact root và các
  contract immutable/checksum hiện có.

## Bằng chứng kiểm thử

- TDD regression test mô phỏng symbolic link tại thư mục cha và xác minh
  `put()` bị từ chối, không tạo file/thư mục phụ.
- Targeted artifact contract: **20 passed, 1 skipped**. Test symbolic link vật
  lý bị skip vì Windows runner không có privilege tạo link; guard vẫn được
  kiểm chứng bằng mock fail-closed.

## Kết luận

Artifact path hiện không chấp nhận symbolic link ở identity hoặc bất kỳ
component thư mục cha nào. Đây là bằng chứng offline cho path-safety; live
model-service smoke và production golden parity vẫn cần endpoint, credential và
catalog production thật.
