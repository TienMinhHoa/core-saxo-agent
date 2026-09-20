# Phase 3 — Contract extraction typed

## Phạm vi iteration 5

Chọn lát Clean Code nhỏ nhất của Phase 3: chuẩn hóa DTO đầu vào/đầu ra cho
PDF extraction và giữ nguyên coordinate contract. Chưa nối provider HTTP,
Paddle, CLI cũ hoặc FastAPI route vào contract này.

## Thay đổi

- `PdfExtractionRequest` chỉ nhận document reference, artifact PDF, source
  version, correlation ID và model profile; không chứa local path hay global
  configuration.
- `PdfExtractionResult` chỉ công bố các artifact immutable cho Markdown, layout
  và manifest cùng coordinate evidence.
- `ExtractionCoordinate` buộc ghi rõ coordinate space, PDF page index và dòng
  Markdown; bbox chỉ là dữ liệu tùy chọn trong cùng một space.
- Validation chặn artifact sai loại, vị trí âm/không hợp lệ và bbox không hợp lệ.

## Bằng chứng

- `tests/test_phase_3_extraction_contract.py`: 5 test cases (gồm parametrized
  invalid positions) kiểm tra input, output, coordinate fidelity và validation.
- Lệnh kiểm tra: `uv run pytest tests/test_phase_3_extraction_contract.py`.
- Regression suite cần chạy sau khi ghép lát tiếp theo; iteration này không thay
  đổi orchestration runtime.

## Ranh giới còn lại

`RemotePdfExtractor`, adapter model service và pipeline artifact persistence sẽ
được ghép ở các lát sau; backend vẫn chưa được phép import Paddle/CUDA.
