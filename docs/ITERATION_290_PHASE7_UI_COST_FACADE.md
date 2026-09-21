# Iteration 290 - tach policy format chi phi khoi root UI

## Pham vi

Slice nay tiep tuc Phase 7 Cleanup: policy trinh bay chi phi cua answer-model
duoc dua vao `music_rag.ui_rendering`, cung boundary voi cac helper rendering
UI da co. `app.py` chi con goi facade khi tao output cho Gradio.

## Thay doi

- Them `format_answer_cost()` vao `src/music_rag/ui_rendering.py` va public
  export qua `__all__`.
- Cap nhat `app.py` de dung formatter tu facade, giu nguyen cac truong usage,
  cost, image inputs va thong diep chi phi hien co.
- Mo rong `test_phase_7_legacy_ui_boundary.py` de khoa public helper facade.

## Bang chung

- `uv run pytest -q`: **970 passed, 18 skipped, 1 warning**.
- `uv run python -m compileall -q src app.py tests`: dat.
- `git diff --check`: dat; chi con warning line-ending LF/CRLF cua Git tren
  Windows, khong co whitespace error.
- Cac skip la Gradio/sample source/symbolic-link permission cua moi truong,
  khong phai loi cua slice nay.

## Gioi han con lai

Live model-service smoke va production golden parity van chua the xac minh vi
checkout thieu endpoint, credential va catalog production that.
