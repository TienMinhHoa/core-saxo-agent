# Iteration 306 - public export cua PDF extraction workflow

## Pham vi

Tiep tuc Phase 7 cua `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: giu ranh gioi
public package API on dinh cho workflow PDF sau khi interface da ngung import
module trien khai truc tiep.

## Thay doi

- Khai bao `run_extraction` trong `saxophone.workflows.__all__`.
- Them contract test dam bao ten public xuat hien dung mot lan.
- Khong thay doi behavior cua workflow, route HTTP, hay legacy wrapper.

## Bang chung

- Targeted: `uv run pytest tests/test_phase_7_pdf_layout_wrapper.py -q` - dat
  5 tests.
- Full offline: se chay sau khi thay doi hoan tat.
- Live model-service smoke va production parity van chua xac minh do checkout
  thieu endpoint, credential va production catalog that.

## Ket luan

Public API cua package workflow nay da dong bo voi boundary ma adapter PDF dang
su dung; day la mot buoc cleanup nho, doc lap va co the kiem chung trong Phase 7.
