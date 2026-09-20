# Iteration 39 - Khong danh dau indexed voi projection rong

## Pham vi

Khoa mot bien hop dong nho cua Phase 4 trong `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`:
`IndexDocument` chi duoc bao cao `indexed=True` khi co it nhat mot chunk da duoc
embed va san sang ghi vao vector index.

Truoc thay doi, danh sach record rong van di qua nhanh thanh cong, goi upsert
khong co du lieu va tao report thanh cong. Trang thai nay lam sai nghia cua bao
cao ingestion va co the lam workflow hieu nham rang tai lieu da searchable.

## Thay doi

- Them contract test cho projection rong: khong goi embedding provider, khong goi
  vector index, report co `indexed=False` va loi typed qua `errors`.
- `IndexDocument.execute` tra failure report voi loi `cannot index an empty
  projection` truoc moi side effect embedding/indexing.
- Bao toan cac counter ve chunk/paragraph o gia tri 0 va khong danh dau
  `failed_paragraph_count` cho truong hop khong co input.

## Bang chung kiem thu

```text
uv run pytest tests/test_phase_4_index_document.py -q
17 passed

uv run pytest -q
336 passed, 2 skipped, 1 warning

uv run python -m compileall -q src tests
git diff --check
```

Warning duy nhat la alias `anyio.abc.BlockingPortal` deprecated trong Starlette
TestClient; khong phat sinh tu thay doi iteration nay.

## Gioi han

Live model-service smoke, production catalog parity va deployment van chua the
xac minh vi checkout chua co endpoint/credential/catalog production that.
