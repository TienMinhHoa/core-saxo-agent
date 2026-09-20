# Iteration 81 - Contract metadata Chroma phẳng

## Phạm vi

Siết một lỗ hổng nhỏ trong adapter `ChromaVectorIndex`: metadata dạng list chỉ
được chứa scalar hữu hạn hoặc chuỗi; list lồng nhau không được gửi tới Chroma.

## Thay đổi

- Bổ sung regression test chứng minh metadata `[["page"]]` bị từ chối trước
  provider I/O.
- Tách kiểm tra scalar của phần tử list để giữ contract rõ ràng và fail-closed.

## Bằng chứng kiểm thử

- Targeted: `uv run pytest tests/test_phase_4_ingestion_contract.py`.
- Targeted result: `58 passed`.
- Full suite: `uv run pytest` đạt `444 passed, 2 skipped, 1 warning`.
- `python -m compileall -q src tests` và `git diff --check` đều đạt.
- Live Chroma/model-service smoke chưa chạy trong iteration này vì checkout
  không có endpoint, credential và catalog production được cấp quyền.
