# Iteration 259 - tach retrieval khoi answer generation

## Pham vi

Iteration nay tiep tuc Phase 7 trong `docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`.
Muc tieu la khoa ro quy tac: retrieval chi chon va kiem tra evidence; chat moi
duoc phep phu trach answer generation.

## Thay doi

- Them contract test AST `test_retrieval_does_not_depend_on_answer_generation`.
- Test quet toan bo file Python trong `saxophone.retrieval` va tu choi moi import
  bat dau bang `saxophone.chat`.
- Khong doi logic runtime vi source hien tai da tuan thu boundary; enforcement
  moi giup ngan regression khi them module sau nay.

## Bang chung kiem tra

- `uv run pytest tests/test_phase_7_dependency_enforcement.py -q`: **19 passed**.
- Da giu nguyen boundary: retrieval khong import answer generator/chat.
- Live model-service smoke va production golden parity van chua xac minh vi
  checkout khong co endpoint, credential va catalog production thuc te.

## Trang thai

Quy tac tach retrieval va answer generation da co enforcement rieng, phu hop
voi muc 5 cua phan Dependency enforcement trong ke hoach kien truc.
