# Iteration 62 - Chroma distance không âm

## Phạm vi

Siết boundary của `ChromaSemanticRetriever` theo hướng fail-closed: distance
do Chroma trả về phải là số hữu hạn và không âm trước khi được đổi thành
`semantic_score = 1 - distance`.

## Thay đổi

- Bổ sung regression test cho distance `-0.1` và `-1`.
- Adapter từ chối distance âm bằng `ValueError` với thông báo rõ ràng.
- Không thay đổi mapping hợp lệ hiện có; distance `0.1` vẫn cho score `0.9`.

## Bằng chứng kiểm thử

- TDD red trước implementation: 2 test mới fail vì adapter chưa chặn distance âm.
- Sau implementation: targeted Chroma tests **17 passed**.
- Full suite, compileall và `git diff --check` được chạy ở cuối iteration; kết
  quả ghi trong handoff của iteration.

## Liên hệ yêu cầu kiến trúc

Đây là một phần của yêu cầu Phase 5/Chroma adapter: validate provider result
trước khi tạo `ChunkHit`, không để dữ liệu malformed tạo evidence hoặc score
không hợp lệ.

## Giới hạn xác minh

Chưa chạy live model-service/production parity vì checkout hiện không có
endpoint, credential và production catalog được phê duyệt.
