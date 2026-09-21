# Iteration 206 - contract limiter I/O cua artifact repository

## Pham vi

Tiep tuc Phase 2 trong `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: adapter
filesystem phai chay blocking I/O qua bounded executor. Lat cat nay khoa
dependency injection cua `LocalArtifactRepository` de loi cau hinh duoc phat
hien tai constructor, thay vi loi muon khi `put()` hoac `get()` chay.

## Thay doi

- `LocalArtifactRepository` chap nhan `None` de tao limiter mac dinh.
- Neu truyen gia tri khac `anyio.CapacityLimiter`, constructor fail-fast voi
  `ValueError("io_limiter must be a CapacityLimiter")`.
- Them test cho object, boolean, so nguyen sai kieu va limiter hop le.
- Khong thay doi co che bounded I/O, shared limiter, immutable write hoac
  artifact path safety.

## Bang chung

- Targeted: `uv run pytest tests/test_phase_2_artifact_storage_contract.py -q`
  -> **28 passed, 1 skipped**.
- Skip duy nhat la test symbolic link do Windows checkout thieu quyen tao link;
  day la han che moi truong, khong phai test failure.

## Gioi han con lai

Live model-service smoke va production golden parity van chua xac minh vi
checkout chua co endpoint, credential va production catalog thuc.
