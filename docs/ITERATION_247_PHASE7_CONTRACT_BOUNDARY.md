# Iteration 247 — Khóa dependency của domain contract

## Phạm vi

Tiếp tục Phase 7 của `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md` với một lát cắt nhỏ:
đảm bảo các file `models.py` và `ports.py` của package mới không kéo dependency hạ
tầng vào domain/application contract.

## Thay đổi

- Bổ sung test AST `test_domain_models_and_ports_do_not_import_infrastructure` trong
  `tests/test_phase_7_dependency_enforcement.py`.
- Rule fail-closed với `chromadb`, provider SDK, `dotenv` và `fastapi` trên mọi
  `models.py`/`ports.py` dưới `src/saxophone`.
- Giữ rule riêng cho inbound adapter: `fastapi` vẫn hợp lệ tại
  `src/saxophone/interfaces/api.py`; không dùng blacklist chung gây false positive.

## Bằng chứng kiểm thử

- `uv run pytest tests/test_phase_7_dependency_enforcement.py -q`: **8 passed**.
- Test mới chạy cùng 7 dependency checks hiện hữu, không phát hiện vi phạm trong
  checkout hiện tại.
- Live model-service smoke và production parity chưa thể xác minh vì checkout không
  có endpoint, credential và production catalog thật; trạng thái được báo riêng trong
  `docs/LIVE_MODEL_SERVICE_SMOKE_STATUS.md`.

## Kết luận

Lát cắt enforcement của Phase 7 đã được mở rộng từ use case/adapter sang shared
domain contract mà không thay đổi runtime behavior. Chưa đánh dấu hoàn tất toàn bộ
stop condition vì live smoke và production golden parity vẫn là blocker ngoài checkout.
