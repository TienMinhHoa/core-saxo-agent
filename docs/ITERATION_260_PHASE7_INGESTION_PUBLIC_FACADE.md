# Iteration 260 — public facade cho ingestion

## Mục tiêu

Khóa một điểm truy cập công khai cho module `saxophone.ingestion`, để consumer
chỉ phụ thuộc vào contract, chunking và use case; không phải biết các module
implementation như `adapters.py` hoặc `use_cases.py`.

## Thay đổi

- `saxophone.ingestion` export các DTO ingestion, `EmbeddingProvider`,
  `VectorIndex`, `IndexDocument` và `build_source_chunks` qua `__all__`.
- Bổ sung contract test bảo đảm danh sách export tồn tại và mọi symbol đều
  truy cập được từ facade.
- Không export adapter hạ tầng hoặc SDK/provider từ facade.

## Bằng chứng kiểm chứng

- Contract Phase 7: `uv run pytest tests/test_phase_7_dependency_enforcement.py -q`
  → **20 passed**.
- Thay đổi chỉ bổ sung public boundary và test; chưa chạy live model-service.
- Live smoke và production golden parity vẫn chưa xác minh vì checkout thiếu
  endpoint, credential và catalog production thật.

## Kết luận

Module ingestion hiện có public API rõ ràng, phù hợp dependency inversion và
giảm coupling của consumer với cấu trúc file nội bộ.
