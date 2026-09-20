# Iteration 93 — Chroma reserved result metadata

## Mục tiêu

Tiếp tục thực hiện yêu cầu metadata projection trong
`docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: kết quả search từ Chroma không
được làm mất identity/provenance của chunk.

## Thay đổi

- Giữ nguyên kiểm tra `metadata.chunk_id` phải là chuỗi không rỗng và khớp row
  ID.
- Bổ sung fail-closed cho các reserved field nếu provider trả về chúng:
  `document_ref`, `source_version`, `embedding_profile` và `access_scope` phải
  là chuỗi không rỗng.
- Không tự bù giá trị thiếu; metadata sai bị từ chối trước khi tạo `VectorHit`.

## Bằng chứng kiểm thử

- Test regression mới bao phủ blank string, số và list ở reserved metadata.
- `uv run pytest tests/test_phase_4_ingestion_contract.py -q`: 81 passed.
- `uv run pytest -q`: sẽ chạy sau khi hoàn tất iteration.
- `python -m compileall -q src tests` và `git diff --check`: chạy trong bước
  kiểm chứng cuối.

## Giới hạn xác minh

Đây là kiểm chứng offline với fake provider. Live model-service smoke và
production golden parity vẫn cần endpoint, credential và catalog production
được cấp trong môi trường chạy thật.
