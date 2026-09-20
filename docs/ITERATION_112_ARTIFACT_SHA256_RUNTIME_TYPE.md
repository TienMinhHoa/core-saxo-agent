# Iteration 112 - kiểu runtime của checksum artifact

## Phạm vi

Tiếp tục refactor theo `docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`, tập trung
vào contract `ArtifactRef` trước khi filesystem adapter thực hiện I/O.

## Thay đổi

- `ArtifactRef` nay kiểm tra `sha256` là chuỗi trước khi chạy regex digest.
- Giá trị `None`, số, bytes hoặc boolean bị từ chối bằng `ValueError` nhất quán,
  thay vì để `re.fullmatch` phát sinh `TypeError` ngoài contract domain.
- Bổ sung regression tests cho các kiểu runtime không hợp lệ.

## Bằng chứng kiểm thử

- Targeted: `uv run pytest tests/test_phase_2_artifact_reference_contract.py`
- Full suite: sẽ chạy sau khi hoàn tất thay đổi iteration.
- Live model-service smoke và production golden parity chưa thể chạy vì checkout
  chưa có endpoint, credential và catalog production được phê duyệt.

## Kết luận

Contract checksum đã fail-closed tại domain boundary, trước mọi filesystem I/O.
