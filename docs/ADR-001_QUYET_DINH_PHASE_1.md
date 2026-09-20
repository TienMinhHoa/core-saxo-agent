# ADR-001: Chốt các quyết định mở để bắt đầu Phase 1

- Trạng thái: Đã chấp thuận
- Ngày: 20-09-2026
- Phạm vi: backend FastAPI modular monolith; không thay đổi thuật toán OCR, RAG
  hoặc UI legacy trong ADR này.

## Bối cảnh

`SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`, mục 27, yêu cầu chốt các lựa chọn
vận hành trước khi viết `create_app()`, settings và `RemoteGpuGateway`. Các
lựa chọn dưới đây dùng phương án Clean Code: giữ tương thích hiện tại ở rìa hệ
thống, nhưng đặt một contract rõ ràng tại ranh giới mới. Chúng không khẳng định
rằng GPU server hay object storage đã được triển khai.

## Quyết định

| Vấn đề mở | Quyết định được chọn | Lý do và hệ quả kiểm chứng được |
|---|---|---|
| Input ingestion chuẩn | **Header chunks** là input chuẩn trong giai đoạn migration. Structured Markdown vẫn được giữ như artifact/provenance. | Đây là đường Chroma hiện hữu; golden fixture `tests/fixtures/golden/header_chunks/` đã khóa hành vi. Use case ingestion sau này nhận header chunks, không tự đọc Markdown thô. |
| Legacy catalog | Giữ dưới dạng **compatibility adapter chỉ đọc** cho đến khi có golden-query parity và ADR retire riêng. | Tránh mất hành vi khi hai nhánh retrieval vẫn cùng tồn tại; không thêm tính năng mới vào catalog. |
| Metadata và job repository | Dùng **JSON file repository** trong Phase 1, sau port async và atomic-write policy; SQLite là quyết định migration riêng khi có yêu cầu đa tiến trình/truy vấn. | Giữ format runtime hiện có để strangler migration; port không được lộ chi tiết JSON. |
| Điều phối pipeline | Upload tạo document workflow chạy tự động các stage hợp lệ: extract → ingest → indexed. API job vẫn cho phép theo dõi/cancel, không cho route gọi trực tiếp GPU. | Đáp ứng mục tiêu upload đến indexed trong một app, đồng thời trạng thái từng stage vẫn persist được. |
| Job `running` sau restart | Khi startup, supervisor **reconcile bằng poll remote job trước**. Không thấy remote job hoặc lỗi không thể xác minh thì đánh dấu `requires_attention`; tuyệt đối không tự submit lại. | Ngăn OCR/embedding bị chạy trùng; resume có bằng chứng `remote_job_id` đã persist. |
| API/version tương thích | API target dùng prefix **`/api/v1`**. Route layout hiện hữu chỉ được giữ qua adapter deprecation cho đến khi contract test xác nhận parity. | Có một public API rõ ràng mà không big-bang bỏ client hiện hữu. |
| Artifact giữa backend/GPU | Dùng **controlled HTTPS artifact URI** (upload/download service) với TTL, allowlist host, `size_bytes` và SHA-256; không truyền local path, `file://`, UNC hay relative path. | Phù hợp draft contract và có thể test offline bằng validator; chọn này không ép phải dựng object storage ngay. |
| Xác thực và transport GPU | Bắt buộc HTTPS, bearer token cấu hình tập trung tại `AppSettings`; kiểm tra chứng chỉ bật mặc định. mTLS là nâng cấp vận hành sau khi có hạ tầng certificate. | Đủ đơn giản cho một backend/remote server, không đưa secret vào route/use case/manifest. |
| Model/profile | Mỗi `task_type` phải ánh xạ vào profile name/version nằm trong allowlist cấu hình. Request không được tự chọn model path hoặc profile tùy ý. | Gateway và fake-server contract có thể từ chối profile không được phê duyệt trước khi submit. |
| Timeout, retry, concurrency | Các ngưỡng là typed settings với default an toàn: timeout theo từng HTTP request, retry bounded cho lỗi transport/5xx/429 có backoff+jitter, và giới hạn in-flight. Lỗi schema/checksum/4xx nghiệp vụ không retry. | Tách policy khỏi route/use case; giá trị số được điều chỉnh bằng cấu hình sau smoke/load measurement, không bịa tối ưu sớm. |
| Retention | Artifact/result remote được giữ **30 ngày mặc định**, cấu hình được; metadata và audit tối thiểu giữ lâu hơn theo policy vận hành. Cleanup chỉ xóa artifact đã ở terminal và không còn reference. | Có lifecycle rõ ràng nhưng không xóa dữ liệu during migration; implementation phải có test reference guard trước khi bật cleanup. |

## Ranh giới không thay đổi

1. Backend không chạy Paddle, CUDA, OCR, VLM, embedding hoặc LLM local.
2. Chroma tiếp tục là vector index; source document và provenance không được
   coi là chỉ tồn tại trong Chroma.
3. Không xóa `app.py`, `pdf_layout_web.py` hoặc legacy catalog trong Phase 1.
4. Mọi remote task phải đi qua `RemoteGpuGateway` với submit/poll/cancel async
   và result manifest được validate.

## Bằng chứng từ checkout hiện tại

| Nhận định | Bằng chứng |
|---|---|
| Header-chunk là đường cần bảo toàn trước | `src/music_rag/chroma_chunks.py`; fixture và test `tests/test_header_chunk_golden.py`. |
| Sidecar Chroma đang hydrate source/metadata | `tests/test_chroma_sidecar_contract.py` và `docs/PHASE_0_CHROMA_SIDECAR_CONTRACT.md`. |
| Job layout hiện chưa có remote mapping/recovery | `src/pdf_layout_web.py` và `docs/PHASE_0_BASELINE_VA_BEHAVIOR_MAP.md`. |
| Các task GPU hiện chạy cục bộ hoặc gọi provider trực tiếp | Bảng inventory trong `docs/PHASE_0_REMOTE_GPU_CONTRACT_DRAFT.md`. |
| Remote contract đã quy định URI/checksum/schema | `docs/PHASE_0_REMOTE_GPU_CONTRACT_DRAFT.md`, các phần Submit và Result manifest. |

## Tiêu chí hoàn thành cho lát cắt kế tiếp

Lát cắt Phase 1 kế tiếp chỉ được tạo package `saxophone`, typed `AppSettings`,
composition root và health endpoint. Trước implementation, cần viết test cho:

1. settings từ environment và lỗi cấu hình thiếu/không hợp lệ;
2. `create_app()` chỉ tạo một FastAPI app và không khởi tạo provider khi import;
3. health báo tình trạng gateway qua fake port, không gọi GPU thật.

Các kiểm tra trên là offline. Chúng không phải bằng chứng GPU server, TLS,
artifact service hay Chroma thật đang hoạt động.
