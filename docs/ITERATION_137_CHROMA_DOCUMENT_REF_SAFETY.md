# Iteration 137 - an toan document_ref tai Chroma adapter

## Pham vi

Khoa mot lo hong nho tai boundary `ChromaVectorIndex.list_chunk_ids()`: truoc day
adapter chi tu choi gia tri rong, nen van co the gui document reference co dau
`/`, `\\`, control character hoac Unicode khong NFC vao provider.

## Thay doi

- Tai su dung policy `is_safe_document_reference()` cua domain documents trong
  `src/saxophone/ingestion/adapters.py`.
- Tu choi fail-closed truoc provider I/O doi voi blank, khong phai chuoi,
  traversal, slash, control character va Unicode decomposed.
- Mo rong contract test de bao phu day du cac nhom gia tri khong an toan.

## Bang chung

- Targeted: `uv run pytest tests/test_phase_4_ingestion_contract.py -k list_chunk_ids_rejects_invalid_document_ref --basetemp=.pytest-tmp-137`
- Ket qua: **9 passed**.
- Da kiem tra diff: khong co background process nao duoc khoi dong trong iteration.

## Gioi han

Day la kiem tra offline cua adapter; chua thay the production Chroma smoke hoac
live model-service smoke. Endpoint, credential va production catalog van chua
duoc cung cap trong checkout nay.
