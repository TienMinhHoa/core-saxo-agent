# Iteration 258 - chat dung retrieval public facade

## Pham vi

Iteration nay tiep tuc Phase 7 trong `docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`.
Muc tieu la dam bao toan bo module `chat`, bao gom adapter tao cau tra loi,
chi phu thuoc hop dong retrieval cong khai thay vi import truc tiep module trien khai.

## Thay doi

- Mo rong enforcement AST trong `tests/test_phase_7_dependency_enforcement.py` de quet
  moi file Python trong `saxophone.chat`, khong chi `chat.service`.
- Cam import truc tiep `saxophone.retrieval.adapters`, `candidates`, `models`, `ports`
  va `use_cases` tu chat.
- Chuyen `chat.remote_answer` sang import `EvidenceBundle` tu `saxophone.retrieval`
  public facade.

## Bang chung kiem tra

- `uv run pytest tests/test_phase_7_dependency_enforcement.py -q`: **18 passed**.
- `uv run pytest -q`: **939 passed, 18 skipped, 1 warning**.
- `python -m compileall -q src tests`: **dat**.
- `git diff --check`: **dat**.

## Trang thai

Lop phu thuoc chat/retrieval da duoc khoa o muc public facade trong kiem tra offline.
Live model-service smoke va production golden parity van chua xac minh vi checkout
khong co endpoint, credential va catalog production thuc te.
