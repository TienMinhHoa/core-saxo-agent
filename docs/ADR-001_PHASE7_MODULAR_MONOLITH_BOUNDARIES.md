# ADR-001: Ranh giới modular monolith sau Phase 7

- **Trạng thái:** Đã chấp nhận
- **Ngày:** 2026-09-21
- **Phạm vi:** `saxophone-rag-backend`

## Bối cảnh

Phase 7 yêu cầu dọn dẹp legacy nhưng vẫn bảo toàn khả năng tương thích cho đến
khi có parity và quyết định migration riêng. Nếu chỉ dựa vào các ghi chú
iteration, quyết định kiến trúc dễ bị phân tán và có thể bị đảo ngược bởi một
lần chỉnh packaging hoặc entrypoint sau này.

## Quyết định

1. `saxophone-api` là web entrypoint backend duy nhất; composition root tạo
   FastAPI app và route không tự khởi tạo provider/database/GPU SDK.
2. `extraction`, `ingestion`, `retrieval` và `chat` giao tiếp qua public
   contract/port; adapter cụ thể được lắp tại composition root.
3. OCR/VLM/embedding/LLM chạy qua `LiteLLMModelClient` trực tiếp, trả typed
   result/error; backend không sở hữu remote job ID, submit/poll hay job-status
   contract của model service.
4. Wheel backend chỉ đóng gói `music_rag*` và `saxophone*`. Paddle, CUDA,
   model weight và package `extracted*` là compatibility/provider boundary,
   không phải runtime dependency của backend.
5. `app.py`, `pdf_layout_web.py` và các adapter legacy chỉ còn wrapper hoặc
   compatibility/reference. Chỉ retire sau khi golden parity production và
   migration decision được ghi nhận.
6. Mọi blocking filesystem/Chroma I/O đi qua bounded executor; artifact trao
   đổi với model service phải dùng URI có kiểm soát, giới hạn kích thước và
   checksum.

## Hệ quả

- Backend có thể build và chạy trong môi trường không GPU, không CUDA và không
  Paddle; workload GPU phải do model service bên ngoài cung cấp.
- Compatibility code vẫn tồn tại trong source nên không được suy ra rằng
  production parity đã hoàn tất chỉ vì offline test xanh.
- Live model-service smoke và production golden parity là điều kiện độc lập,
  cần endpoint, credential và catalog thật; checkout hiện tại chưa có các
  điều kiện đó.

## Bằng chứng kiểm chứng tại Iteration 355

- Contract Phase 7 và full offline suite đã được các iteration trước ghi nhận
  xanh; lần kiểm tra hiện tại giữ nguyên source/runtime, chỉ chuẩn hóa quyết
  định thành ADR.
- Packaging boundary: `tests/test_phase_7_dependency_enforcement.py` xác nhận
  chỉ có `music_rag*` và `saxophone*`, đồng thời chặn `extracted*`.
- Entrypoint/runbook: `saxophone-api` là script backend duy nhất theo cùng
  contract test.
- Live smoke/production parity vẫn **chưa xác minh**, đúng với
  `docs/LIVE_MODEL_SERVICE_SMOKE_STATUS.md`; không tuyên bố stop condition đã
  hoàn tất.

