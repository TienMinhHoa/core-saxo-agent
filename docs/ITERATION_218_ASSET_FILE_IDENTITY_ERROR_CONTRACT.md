# Iteration 218 - Hop dong loi danh tinh file cua asset

## Pham vi

Tiep tuc harden asset endpoint theo yeu cau file safety trong
`docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: loi `FileExistsError` tu artifact
repository (vi du artifact identity la symbolic link hoac khong phai file hop
le) khong duoc ro ri thanh HTTP 500.

## Thay doi

- Them contract test cho `GET /api/v1/assets/{asset_ref}` khi repository tu
  choi file identity.
- Map `FileExistsError` thanh HTTP 404 voi thong bao trung lap voi asset khong
  ton tai. Endpoint khong tiet lo chi tiet filesystem va van giu mapping
  PermissionError -> 403, ValueError -> 422.

## Bang chung xac minh

- Targeted: `uv run pytest tests/test_phase_7_api_routes.py -q
  --basetemp=.pytest-tmp-218` -> **38 passed, 1 warning**.
- Full offline: `uv run pytest -q --basetemp=.pytest-tmp-218-full` ->
  **906 passed, 3 skipped, 1 warning**.
- Cac skip la dependency/sample/symbolic-link capability cua moi truong; khong
  phai regression cua thay doi nay.
- Live model-service smoke va production parity van chua xac minh vi checkout
  khong co endpoint, credential va production catalog that.

## Ket luan

Asset route fail-closed hon tai boundary HTTP: loi identity noi bo duoc map
thanh not-found an toan, khong lam lo chi tiet filesystem.
