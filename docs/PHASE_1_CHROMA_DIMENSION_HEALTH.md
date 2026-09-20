# Evidence Phase 1: Chroma kiểm tra embedding dimension

## Phạm vi

Lát cắt này bảo vệ invariant trong mục 17.2 của
`SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: collection Chroma phải dùng cùng
embedding dimension với `AppSettings` trước khi application phục vụ ingestion
hoặc retrieval.

## Thay đổi

- Composition root tạo collection với metadata `embedding_dimension` và
  `schema_version` ổn định.
- Nếu collection đã tồn tại và metadata ghi dimension khác cấu hình, startup
  fail-fast bằng `ValueError`; không âm thầm truy vấn index sai chiều.
- Metadata thiếu dimension vẫn được giữ tương thích với collection legacy; việc
  chuẩn hóa metadata legacy là một migration riêng, không tự ý sửa dữ liệu.

## Bằng chứng kiểm thử

- `uv run pytest tests/test_phase_1_composition_root.py -q`
  - kiểm tra metadata được truyền khi compose collection.
  - kiểm tra dimension mismatch bị từ chối.
- `uv run pytest -q`
- `uv run python -m compileall -q src tests`
- `git diff --check`

Các lệnh trên là kiểm thử offline; chưa phải live smoke test với Chroma
production hoặc model service thật.
