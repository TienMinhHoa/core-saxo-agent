# Trạng thái live smoke model service

## Phạm vi

Tài liệu này tách riêng bằng chứng live model-service khỏi kết quả unit,
contract và integration test offline, theo mục 21.1 và tiêu chí nghiệm thu 14
trong `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`.

## Trạng thái hiện tại

**Chưa xác minh live — không có endpoint model service được cung cấp trong
checkout này.** Vì vậy chưa được kết luận rằng remote GPU/model service đang
ready, cũng chưa được kết luận workflow extraction, embedding, tagging hoặc
answer chạy thành công qua dịch vụ thật.

## Bằng chứng đã xác minh offline

```text
uv run pytest -q
291 passed, 2 skipped
```

Các test trên dùng fake gateway, HTTP mock hoặc Chroma `PersistentClient` cục
bộ. Chúng xác minh contract, timeout, capability projection, validation output,
composition và lifecycle; chúng không thay thế live smoke. Bằng chứng offline
hiện tại được đối chiếu với `docs/REFACTOR_ACCEPTANCE_STATUS.md` và phải được
cập nhật cùng lúc khi số test thay đổi.

## Cách xác minh khi có endpoint thật

Chỉ chạy khi đã có `SAXO_REMOTE_GPU_BASE_URL`,
`SAXO_REMOTE_GPU_BEARER_TOKEN` và `SAXO_LITELLM_ENDPOINT` hợp lệ trong môi
trường chạy, không ghi token vào log hoặc tài liệu:

1. Gọi `GET {SAXO_REMOTE_GPU_BASE_URL}/v1/health` và ghi nhận `status` cùng
   capability names; không ghi response chứa thông tin nhạy cảm.
2. Gửi một request nhỏ tới `SAXO_LITELLM_ENDPOINT` cho từng task type được
   công bố: extraction, embedding, tagging và answer.
3. Chạy một workflow xuyên suốt từ artifact đầu vào đến kết quả typed; kiểm tra
   provenance, kích thước embedding, metadata search và lỗi invalid output.
4. Ghi thời điểm, endpoint không chứa secret, task đã chạy và kết quả
   pass/fail vào tài liệu này.

## Giới hạn và quyết định

Lát cắt này không tạo local GPU fallback, không thêm CUDA/Paddle/model weight
vào backend và không đánh dấu stop condition là hoàn tất. Khi có môi trường
remote thật, lần sau chỉ cần cập nhật phần trạng thái và chạy smoke theo các
bước trên.
