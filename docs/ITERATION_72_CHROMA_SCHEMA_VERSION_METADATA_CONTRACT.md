# Iteration 72 - hợp đồng metadata schema version của Chroma

## Phạm vi

Siết boundary `create_chroma_vector_index`: nếu collection Chroma có trường
`schema_version`, trường này phải là chuỗi không rỗng trước khi được so sánh
với schema hiện hành `saxo-chunk-v1`. Collection cũ không có metadata này vẫn
được giữ tương thích như quyết định ở iteration 70.

## Thay đổi

- Reject fail-closed các giá trị `bool`, số, chuỗi rỗng và chuỗi chỉ có
  whitespace với lỗi `schema version metadata is invalid`.
- Giữ nguyên việc reject schema version khác `saxo-chunk-v1`.
- Bổ sung test parameterized tại
  `tests/test_phase_1_composition_root.py`.

## Bằng chứng kiểm tra

- Targeted: `uv run pytest tests/test_phase_1_composition_root.py -q`.
- Full suite, compileall và `git diff --check` sẽ được chạy sau targeted test.
- Đây là kiểm tra offline; live model-service smoke và production parity vẫn
  chưa thể xác minh vì checkout chưa có endpoint, credential và catalog thật.
