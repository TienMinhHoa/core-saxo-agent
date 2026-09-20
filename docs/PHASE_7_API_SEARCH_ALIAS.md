# Evidence Phase 7: API search alias

## Phạm vi

Bổ sung endpoint `POST /api/v1/search` theo target API contract trong
`SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`. Endpoint này là compatibility alias
cho retrieval facade hiện có; không tạo thêm retrieval path hoặc gọi trực tiếp
Chroma/provider SDK.

## Thay đổi

- Thêm route `/api/v1/search` trong inbound adapter.
- Route ủy quyền cho cùng handler `/api/v1/retrieval/evidence`, giữ nguyên
  chuẩn hóa query, giới hạn kết quả, response `EvidenceBundle` và trạng thái
  capability `503` khi chưa compose retrieval.
- Thêm API regression test xác minh alias gọi đúng application facade.

## Bằng chứng xác minh

- Targeted: `uv run pytest tests/test_phase_7_api_routes.py -k search_route`
  — 1 passed.
- Full suite và compile/diff check được ghi nhận ở handoff iteration sau khi
  hoàn tất slice này.

## Giới hạn còn lại

Các endpoint document detail/layout/assets trong target contract chưa được mở
rộng trong iteration này vì cần chốt metadata lookup contract tương ứng.
