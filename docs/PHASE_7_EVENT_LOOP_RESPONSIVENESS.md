# Bằng chứng Phase 7: event loop vẫn đáp ứng khi Chroma blocking

## Phạm vi

Lát cắt này khóa tiêu chí kiến trúc rằng lời gọi Chroma blocking không được
chạy trực tiếp trên event loop. Adapter phải chuyển truy vấn sang worker thread
và vẫn cho coroutine khác được thực thi trong lúc truy vấn đang chờ.

## Thay đổi

Thêm `test_chroma_blocking_query_does_not_starve_event_loop` vào
`tests/test_phase_7_bounded_blocking_io.py`. Test dùng collection giả có truy vấn
chậm, chạy đồng thời một ticker async, rồi yêu cầu ticker quan sát được nhiều
nhịp trước khi truy vấn hoàn tất. Đây là contract hành vi, không phụ thuộc Chroma
server hay model service thật.

## Bằng chứng kiểm thử

```text
uv run pytest -q tests/test_phase_7_bounded_blocking_io.py
3 passed
```

Kết quả chứng minh `ChromaVectorIndex.search()` không khóa event loop trong khi
blocking query chạy qua bounded I/O boundary. Chưa phải live smoke với Chroma
production nhiều worker.
