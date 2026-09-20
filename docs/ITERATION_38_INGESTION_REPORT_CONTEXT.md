# Iteration 38 - Bao toan context paragraph trong ingestion report

## Pham vi

Hoan thien mot gap nho cua Phase 4 trong `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`:
`IngestionReport` phai phan anh dung so paragraph da xu ly, khong suy dien tu so
chunk da tao index. Dieu nay giu duoc audit context khi mot chunk chua nhieu paragraph.

## Thay doi

- `IndexDocument.execute` nhan context tuy chon `paragraph_count` va
  `tagged_paragraph_count`, dong thoi validate hai gia tri khong am va nhat quan.
- `IngestDocument` truyen so paragraph thuc te va so paragraph da tag vao
  `IndexDocument` ca tren nhanh thanh cong lan nhanh loi embedding/index.
- Caller cu cua `IndexDocument` van tuong thich: neu khong truyen context, gia tri
  mac dinh van duoc tinh tu so record.
- Them regression test cho truong hop mot chunk co hai paragraph, bao dam report
  tra ve `chunk_count=1` nhung `paragraph_count=2`.

## Bang chung kiem thu

```text
uv run pytest tests/test_phase_4_ingest_document.py -q
3 passed
```

Ket qua bo sung:

```text
uv run pytest -q
335 passed, 2 skipped, 1 warning
uv run python -m compileall -q src tests
git diff --check
```

`compileall` va `git diff --check` deu thanh cong. Warning duy nhat den tu alias
deprecated cua Starlette trong `TestClient`, khong phai code iteration nay.

## Gioi han

Live model-service smoke, production catalog parity va deployment van chua the
xac minh vi checkout chua co endpoint/credential/catalog production that.
