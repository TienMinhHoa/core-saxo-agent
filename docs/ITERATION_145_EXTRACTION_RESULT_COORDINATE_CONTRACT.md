# Iteration 145 - Siết kiểu dữ liệu tọa độ trong kết quả extraction

## Mục tiêu

Đảm bảo `PdfExtractionResult` chỉ nhận danh sách tọa độ bất biến và đúng kiểu
`ExtractionCoordinate` trước khi kết quả được chuyển sang persistence hoặc ingestion.

## Thay đổi

- Từ chối `coordinates` dạng `list` hoặc container runtime khác `tuple`.
- Từ chối mọi phần tử không phải `ExtractionCoordinate`.
- Giữ nguyên kết quả hợp lệ dạng `tuple[ExtractionCoordinate, ...]` và các kiểm tra artifact hiện có.

## Bằng chứng kiểm thử

- Regression tests: `uv run pytest tests/test_phase_3_extraction_contract.py`.
- Full suite: `uv run pytest --basetemp=.pytest-tmp`.
- Kiểm tra cú pháp: `uv run python -m compileall -q src tests` và `git diff --check`.

## Giới hạn xác minh

Đây là kiểm thử offline. Live model-service smoke và production golden parity chưa chạy
vì checkout chưa có endpoint, credential và catalog production được phê duyệt.
