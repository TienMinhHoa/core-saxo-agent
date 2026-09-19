# Golden fixture cho sidecar Chroma

Fixture này khóa hợp đồng hiện tại của `load_chunk_records()` trước khi tách
`chroma_chunks.py` thành ingestion use case và adapter.

- `header_chunks.json` là đầu vào header-chunk tối thiểu, có provenance trang,
  Markdown image và một VLM presentation block.
- `figure-vlm-results.jsonl` là kết quả VLM hợp lệ duy nhất được phép làm giàu
  metadata ảnh.
- Test không cần Chroma, OpenAI hay GPU: nó chỉ chụp contract chuẩn hóa được
  ghi vào `chunk-records.json`.
