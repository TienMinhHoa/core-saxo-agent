# Bằng chứng Iteration 71 — contract metadata collection Chroma

## Phạm vi

Iteration 70 đã kiểm tra `schema_version` của collection Chroma. Iteration 71
khóa phần còn lại ngay tại composition boundary: metadata do Chroma trả về
phải là mapping; `embedding_dimension` đã lưu phải là số nguyên dương thật,
không nhận `bool` dù Python coi `bool` là một subclass của `int`.

Mục tiêu là fail-closed trước khi application wiring tạo `ChromaVectorIndex`,
tránh tiếp tục với metadata sai kiểu hoặc đánh giá nhầm `True` là dimension 1.

## Thay đổi

- `create_chroma_vector_index` kiểm tra kiểu metadata bằng `Mapping`.
- `embedding_dimension` hiện tại chỉ hợp lệ khi có kiểu chính xác là `int` và
  lớn hơn 0; dimension khác cấu hình vẫn bị từ chối như trước.
- Bổ sung regression tests cho metadata dạng list và dimension dạng `bool`.
- Giữ tương thích với collection cũ không có metadata (`None`): trường hợp
  này vẫn được coi là metadata rỗng và tiếp tục qua các kiểm tra hiện hữu.

## Bằng chứng kiểm thử

Đã chạy:

```text
uv run pytest -q tests/test_phase_1_composition_root.py -k "chroma"
5 passed, 19 deselected, 1 warning
```

Kiểm tra bổ sung:

```text
uv run pytest -q
416 passed, 2 skipped, 1 warning

python -m compileall -q src tests
git diff --check
```

Hai lệnh kiểm tra tĩnh đều hoàn tất không lỗi.

## Giới hạn còn lại

Live model-service smoke và production golden parity vẫn chưa xác minh vì
checkout chưa có endpoint, credential và catalog production thật.
