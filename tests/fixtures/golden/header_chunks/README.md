# Golden fixture: header chunks theo trang

Fixture này khóa contract hiện có của `extracted.extract_header_chunks.extract_chunks`
trước khi migration tách ingestion thành module mới.

`page_aware_sections.md` có hai section `##`, một heading con, hai mốc trang và
một dòng phân cách. `page_aware_sections.expected.json` là output đã được khóa:

- Mốc `## Page N` chỉ là provenance, không phải một chunk.
- Heading `###` nằm trong content của section cha.
- `page_start`/`page_end` phản ánh đúng section kéo qua hai trang.
- Dòng `---` và khoảng trắng biên bị chuẩn hóa.

Bằng chứng offline: chạy
`uv run pytest tests/test_header_chunk_golden.py --basetemp=.pytest-tmp`.
Test không gọi Chroma, provider hay GPU server; pass chỉ xác minh contract
extraction/chunking cục bộ.
