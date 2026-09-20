# Phase 1 - Hợp đồng settings cho Chroma và embedding

## Phạm vi lát cắt

Theo hướng Clean Code được chọn, composition root nhận một `AppSettings` đã
được kiểm tra trước khi tạo adapter Chroma. Lát cắt này chỉ chuẩn hóa ba giá
trị cần cho lifecycle tiếp theo; chưa khởi tạo client/collection production và
chưa tuyên bố đã có live Chroma smoke test.

## Hợp đồng

- `SAXO_CHROMA_PERSIST_DIRECTORY`: thư mục persist, mặc định nằm dưới
  `SAXO_DATA_ROOT/chroma`; giá trị rỗng hoặc relative path đi qua `..` bị từ
  chối.
- `SAXO_CHROMA_COLLECTION_NAME`: tên collection 3-63 ký tự, bắt đầu/kết thúc
  bằng chữ hoặc số, phần giữa chỉ dùng chữ, số, `_`, `-`.
- `SAXO_EMBEDDING_DIMENSION`: số nguyên dương, mặc định `1536`.

Các giá trị được giữ typed trong `AppSettings`, không đọc environment trong
module runtime khi import. Điều này tạo seam rõ ràng để vòng sau compose
`ChromaVectorIndex` và kiểm tra dimension collection trước khi phục vụ search.

## Bằng chứng kiểm tra

```text
uv run pytest -q tests/test_phase_1_settings.py
25 passed

python -m compileall -q src tests
pass

git diff --check
pass (chỉ còn cảnh báo chuyển LF/CRLF của Git trên Windows)
```

## Giới hạn còn lại

Chưa có Chroma client production được tạo từ các settings này, chưa kiểm tra
collection dimension thực tế và chưa chạy live model-service/Chroma smoke test.
