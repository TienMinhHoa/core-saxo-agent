# Iteration 129 — MIME quoted-string có dấu chấm phẩy

## Phạm vi

Tiếp tục siết contract `ArtifactRef.media_type` theo kế hoạch kiến trúc. Lát cắt
này xử lý trường hợp MIME parameter dùng quoted-string và giá trị hợp lệ chứa
dấu `;`.

## Thay đổi

- Parser không còn dùng `split(";")` mù: dấu `;` bên trong quoted-string được
  giữ nguyên trong cùng một parameter.
- Quote hoặc escape chưa đóng bị từ chối fail-closed.
- Bổ sung regression tests cho quoted value có `;` và hai dạng quote lỗi.

## Bằng chứng kiểm thử

- `uv run pytest tests/test_phase_2_artifact_reference_contract.py -q`: **58 passed**.
- `uv run pytest -q`: **564 passed, 3 skipped, 1 warning**.
- `python -m compileall -q src tests`: đạt.
- `git diff --check`: đạt.

## Giới hạn còn lại

Live model-service smoke và production golden parity vẫn chưa chạy được vì
checkout chưa có endpoint, credential và production catalog được phê duyệt.
