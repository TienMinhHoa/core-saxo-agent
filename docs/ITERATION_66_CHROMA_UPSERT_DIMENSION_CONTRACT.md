# Iteration 66 — hợp đồng dimension khi upsert Chroma

## Phạm vi

Khóa một lát cắt nhỏ của yêu cầu Chroma trong `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`:
mọi vector phải có dimension đúng với logical collection trước khi gọi SDK Chroma.

## Thay đổi

- `create_chroma_vector_index` truyền `AppSettings.embedding_dimension` vào adapter.
- `ChromaVectorIndex.upsert_chunks` fail-fast khi một `ChunkIndexRecord` lệch dimension;
  việc kiểm tra xảy ra trước `anyio.to_thread.run_sync` và trước mọi Chroma I/O.
- Dimension cấu hình không hợp lệ (`< 1`) bị từ chối ngay khi khởi tạo adapter.

## Bằng chứng kiểm chứng

- `uv run pytest tests/test_phase_1_chroma_live_contract.py -q`: **2 passed**.
- Test mới xác nhận record 2 chiều không được ghi vào collection 3 chiều và collection
  vẫn rỗng sau lỗi.
- Sẽ chạy lại full suite, `compileall` và `git diff --check` trước khi kết thúc iteration.

## Giới hạn

Đây là kiểm chứng offline với Chroma local/persistent. Chưa chứng minh model-service thật,
credential, network/TLS hoặc deployment production.
