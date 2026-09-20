# Iteration 89 - Contract `limit` cho Chroma semantic retriever

## Phạm vi

Khóa input contract của `ChromaSemanticRetriever.search` trước khi gọi embedding
provider hoặc Chroma. Tham số `limit` phải là số nguyên dương; `bool`, số thực,
chuỗi và object tùy ý không được phép đi sâu vào request path. Giá trị `limit <= 0`
vẫn giữ hành vi tương thích là trả về danh sách rỗng mà không gọi I/O.

## Thay đổi

- Bổ sung kiểm tra fail-closed cho kiểu của `limit`, loại trừ rõ `bool` vì Python
  coi `bool` là subclass của `int`.
- Bổ sung regression test cho `True`, số thực, chuỗi và object; test xác nhận
  embedding provider không bị gọi khi input sai.

## Bằng chứng

- Targeted: `uv run pytest tests/test_chroma_semantic_retriever.py --basetemp=.pytest-tmp`
  - **23 passed**.
- Full suite: `uv run pytest --basetemp=.pytest-tmp`
  - **467 passed, 2 skipped, 1 warning**.
- Static: `uv run python -m compileall -q src tests` và `git diff --check` - **đạt**.
- Thư mục `.pytest-tmp` còn lại do policy chặn lệnh xóa đệ quy; không có process
  nền nào được khởi chạy.

## Trạng thái

Contract offline đã được khóa. Live model-service smoke và production golden
parity vẫn chưa xác minh vì checkout chưa có endpoint, credential và catalog
production thực tế.
