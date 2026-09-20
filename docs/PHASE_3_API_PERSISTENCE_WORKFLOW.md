# Phase 3 — Nối API process với workflow persist extraction

## Phạm vi iteration 53

Lát cắt này hoàn thiện boundary composition cho đường đi `process` ở API: khi
composition root nhận `ProcessAndPersistDocument`, route sẽ chạy extraction,
nhận payload qua transfer port và ghi ba artifact output (`markdown`, `layout`,
`manifest`) qua `ArtifactRepository`. Khi dependency này không được compose,
route vẫn giữ behavior tương thích bằng `ProcessDocument` hiện có.

## Thay đổi

- `AppOverrides` và `AppContainer` có dependency tùy chọn
  `process_and_persist_document`.
- `create_app()` truyền dependency này vào inbound API adapter.
- Route `POST /api/v1/documents/{document_ref}/process` ưu tiên workflow
  persist; nếu không có thì dùng workflow extraction cũ.
- Thêm API contract test dùng fake extractor, payload provider và repository để
  chứng minh cả ba output artifact được persist.

## Bằng chứng kiểm thử

- Targeted: `uv run pytest tests/test_phase_7_api_routes.py tests/test_phase_3_process_and_persist_document.py -q`
  → **12 passed**.
- Full suite: `uv run pytest -q` → **218 passed, 2 skipped, 1 warning**.
- `python -m compileall -q src` → đạt.
- `git diff --check` → đạt.

Hai test skip là dependency Gradio/sample source không có trong checkout; không
liên quan thay đổi iteration này.

## Ranh giới chưa tuyên bố hoàn tất

Production vẫn chưa tự tạo payload-transfer adapter từ remote model service,
nên chưa thể tuyên bố upload → extraction → persist → ingest → indexed là một
luồng live end-to-end. Iteration này chỉ chứng minh wiring API với workflow đã
có và giữ compatibility path cũ.
