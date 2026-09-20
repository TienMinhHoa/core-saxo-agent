# Iteration 86 — Chroma metadata không cho phép cấu trúc vòng

## Phạm vi

Khóa một lỗi biên trong projection metadata của `ChromaVectorIndex`: mapping
ngoài của `ChunkIndexRecord` là bất biến, nhưng list/tuple nằm bên trong vẫn có
thể tự tham chiếu. Projection cũ sẽ đệ quy vô hạn trước khi provider được gọi.

## Thay đổi

- Projection list/tuple nay theo dõi các container đang đi qua.
- Metadata tự tham chiếu bị từ chối bằng `ValueError` với thông báo rõ ràng.
- Provider Chroma không bị gọi khi metadata không hợp lệ.
- Bổ sung regression test cho list tự tham chiếu.

## Bằng chứng kiểm thử

- Targeted: `uv run pytest tests/test_phase_4_ingestion_contract.py -q` — đạt.
- Full suite, `compileall` và `git diff --check` được chạy sau khi thay đổi.

## Giới hạn còn lại

Live model-service smoke và production golden parity vẫn chưa thể xác minh vì
checkout chưa có endpoint, credential và catalog production thật.
