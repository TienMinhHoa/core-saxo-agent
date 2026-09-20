# Phase 1 - Composition persistent Chroma

## Phạm vi lát cắt

Lát cắt này hoàn thiện phần composition tối thiểu cho vector index production:
`AppSettings` cung cấp thư mục lưu và tên collection, còn composition root tạo
`chromadb.PersistentClient`, lấy collection bằng `get_or_create_collection`, rồi
bọc collection qua `ChromaVectorIndex`. Application vẫn chỉ phụ thuộc port
`VectorIndex`; SDK Chroma chỉ xuất hiện ở adapter composition.

## Thay đổi

- Thêm `create_chroma_vector_index` làm factory hạ tầng, nhận `AppSettings` đã
  validate và trả về adapter async hiện có.
- Default `create_app` tạo `ChromaVectorIndex` từ cấu hình; test override vẫn
  giữ nguyên identity và không bị thay thế.
- Health của default composition phản ánh ingestion là `ready` vì index đã được
  compose, thay vì báo disabled dù adapter đã tồn tại.

## Bằng chứng kiểm thử

```text
uv run pytest -q tests/test_phase_1_composition_root.py tests/test_phase_4_ingestion_contract.py --basetemp=.pytest-tmp
35 passed, 1 warning

python -m compileall -q src tests
pass

git diff --check
pass
```

Test composition dùng fake `chromadb` để xác minh chính xác path persistent và
collection name lấy từ settings, không cần Chroma server hay model service thật.

## Giới hạn còn lại

Chưa có live smoke test với dữ liệu Chroma thật, chưa kiểm tra lifecycle đóng
client riêng của Chroma, và `embedding_dimension` mới được validate ở settings
chứ chưa được đối chiếu với vector/collection metadata khi runtime.
