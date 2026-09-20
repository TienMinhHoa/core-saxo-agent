# Bằng chứng smoke cho backend entrypoint — Phase 7

## Phạm vi iteration 68

Lát cắt này chỉ củng cố hợp đồng vận hành của entrypoint backend duy nhất:

- package script `saxophone-api` phải gọi `saxophone.main:main`;
- `--help` phải trả về thành công mà không khởi động Uvicorn;
- khi chạy thật, CLI phải truyền `host`, `port` và `factory=True` cho
  `saxophone.main:create_application`.

Đây là kiểm tra offline, không cần remote GPU, Chroma hay model service.

## Bằng chứng

Lệnh smoke:

```text
uv run saxophone-api --help
```

Kết quả quan sát được:

```text
usage: saxophone-api [-h] [--host HOST] [--port PORT]
Run the Saxophone RAG backend
```

Contract test:

```text
tests/test_phase_7_backend_entrypoint.py
```

Test xác minh cả hai nhánh: wiring Uvicorn factory với host/port tùy chọn và
nhánh `--help` thoát mã 0 mà không gọi server.

## Giới hạn

Smoke này không chứng minh remote GPU, Chroma, model service hoặc feature
parity với `app.py`. `app.py` vẫn là compatibility path và chỉ được xóa sau
khi có golden/feature-parity evidence cùng migration decision như kế hoạch
kiến trúc yêu cầu.

## Trạng thái kiểm chứng

- `uv run saxophone-api --help`: pass.
- Contract test entrypoint: pass (`2 passed`).
- Full offline suite: pass (`242 passed, 2 skipped, 1 warning`).
- `compileall`: pass.
- `git diff --check`: pass; chỉ còn cảnh báo line ending CRLF của Git trên
  Windows.
- Không khởi động background process.
