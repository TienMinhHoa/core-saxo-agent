# Iteration 239 - dọn client khi tạo collection Chroma thất bại

## Phạm vi

`create_chroma_vector_index()` đã đóng `PersistentClient` khi validation metadata
thất bại, nhưng lỗi từ `get_or_create_collection()` xảy ra trước cleanup guard.
Điều này có thể làm rò rỉ client trong lúc composition root khởi tạo.

## Thay đổi

- Mở rộng cleanup guard bao quanh cả bước tạo/lấy collection và validation metadata.
- Khi collection creation ném lỗi, gọi `client.close()` nếu SDK hỗ trợ.
- Giữ nguyên lỗi gốc nếu cleanup cũng thất bại.
- Thêm regression test chứng minh client được đóng trên collection-creation failure.

## Bằng chứng

- Targeted: `uv run pytest tests/test_phase_1_composition_root.py -q` — **33 passed, 1 warning**.
- Full offline suite, `compileall` và `git diff --check` được chạy sau thay đổi.
- Live model-service smoke và production parity vẫn chưa xác minh do checkout thiếu endpoint,
  credential và catalog production thật.
