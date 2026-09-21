# Iteration 345 — kiểm chứng build package backend

## Phạm vi

Kiểm chứng artifact phân phối của Phase 7 sau khi `saxophone-api` trở thành web
entrypoint duy nhất. Lát cắt này chỉ kiểm tra đóng gói offline; không giả định
đã có model-service production để chạy live smoke.

## Bằng chứng

Đã chạy:

```text
uv build --wheel --out-dir .pytest-tmp-345-build
```

Kết quả: thành công, tạo
`.pytest-tmp-345-build/saxophone_rag_backend-0.1.0-py3-none-any.whl`.

Kiểm tra log build xác nhận wheel chứa package đích `saxophone` cùng các module
`interfaces`, `workflows`, `platform`, `extraction`, `ingestion`, `retrieval`,
`chat`, `tagging` và `documents`; entry-point metadata vẫn chỉ khai báo
`saxophone-api` cho backend web. Module `pdf_layout_web` chỉ còn là compatibility
shim được đóng gói, không tạo console script thứ hai.

## Kết luận

Tiêu chí build/package offline của Phase 7 được xác nhận thêm. Live
model-service smoke và production golden parity vẫn chưa thể xác minh vì
checkout hiện không có endpoint, credential và catalog production thật.
