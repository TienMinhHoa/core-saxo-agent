# Iteration 261 — Extraction public facade

## Mục tiêu

Tiếp tục Phase 7 của kế hoạch refactor: workflow và inbound API phải dùng
contract công khai của module `extraction`, còn adapter cụ thể chỉ được lắp ráp
ở composition root.

## Thay đổi

- Bổ sung `PersistExtractionArtifacts` vào public facade
  `saxophone.extraction`.
- Chuyển `interfaces.api`, `workflows.process_document` và
  `workflows.ingest_extracted_document` sang import từ facade này.
- Thêm enforcement test để ngăn các consumer import trực tiếp `models`,
  `ports` hoặc `persistence` nội bộ của extraction.

## Bằng chứng kiểm tra

- `uv run pytest tests/test_phase_7_dependency_enforcement.py -q`: **22 passed**.
- Đã kiểm tra facade công khai có đủ 9 symbol contract/use-case/adapter được
  phép export và mọi symbol đều truy cập được.
- Chưa chạy live model-service smoke trong iteration này; checkout vẫn thiếu
  endpoint, credential và production catalog thực tế.

## Trạng thái

Đơn vị facade extraction đã được khóa bằng contract test offline. Stop condition
toàn bộ repository chưa kết luận vì các kiểm tra live và production parity vẫn
cần môi trường bên ngoài checkout.
