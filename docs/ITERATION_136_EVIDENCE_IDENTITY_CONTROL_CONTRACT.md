# Iteration 136 - Contract control character cho identity retrieval

## Phạm vi

Tiếp tục harden boundary retrieval -> chat theo tiêu chí EvidenceBundle phải
được validate trước khi sử dụng. Các identity của `ChunkHit`, selected refs và
source-text refs đã yêu cầu trim/NFC nhưng vẫn còn nhận NUL, ASCII control
character hoặc DEL.

## Thay đổi

- Bổ sung policy canonical chung trong retrieval models để từ chối ký tự có mã
  ASCII nhỏ hơn `0x20` hoặc bằng `0x7f`.
- Áp dụng policy cho `ChunkHit.source_ref`, `chunk_ref`,
  `retrieval_version`, `EvidenceBundle` source-text keys, `selected_refs` và
  `image_refs`; nội dung source text vẫn được phép chứa xuống dòng hợp lệ.
- Bổ sung regression tests cho NUL, control character và DEL ở các boundary
  identity; test chứng minh source-text key không an toàn bị chặn trước khi
  evidence được ghép vào bundle.

## Bằng chứng kiểm thử

- `uv run pytest tests/test_phase_5_retrieval_contract.py -q
  --basetemp=.pytest-tmp-136` — **48 passed**.
- `uv run pytest -q --basetemp=.pytest-tmp-136` — **605 passed, 3 skipped,
  1 warning**; một skip là do Windows không có quyền tạo symbolic link.
- `uv run python -m compileall -q src tests` — đạt.
- `git diff --check` — đạt; chỉ còn cảnh báo chuyển đổi LF/CRLF của Git trên
  Windows.
- Trạng thái live model-service smoke/production parity vẫn phụ thuộc endpoint,
  credential và catalog production chưa có trong checkout.

## Trạng thái còn lại

Live model-service smoke và production golden parity chưa thể xác minh trong
checkout hiện tại vì thiếu endpoint, credential và catalog production được phê
duyệt.
