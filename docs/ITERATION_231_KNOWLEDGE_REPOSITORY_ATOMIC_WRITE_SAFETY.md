# Iteration 231 - an toan ghi atomic knowledge sidecar

## Pham vi

Tiep tuc yeu cau file-safety trong `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`
cho `JsonKnowledgeRepository`. Muc tieu cua lat cat nay la khong de qua trinh
ghi JSON tiep tuc neu root, parent hoac target path bi redirect boi symbolic
link trong khoang giua `mkdir`, tao file tam va `os.replace`.

## Thay doi

- Them kiem tra symbolic-link path truoc va sau khi tao parent directory.
- Them lan kiem tra cuoi ngay truoc `os.replace`, de fail-closed neu path thay
  doi trong luc file tam dang duoc tao.
- Them regression test mo phong root bi redirect ngay sau `mkdir`; tren Windows
  hien tai test filesystem symlink duoc skip co kiem soat do thieu quyen
  `WinError 1314`.

## Bang chung kiem thu

- `uv run pytest tests/test_phase_2_json_knowledge_repository.py -q`: **6 passed,
  4 skipped**.
- `uv run pytest --basetemp=.pytest-tmp -q`: **916 passed, 18 skipped, 1 warning**.
- `python -m compileall -q src tests`: **dat**.
- `git diff --check`: **dat**; chi con canh bao line-ending LF/CRLF cua Git.

## Trang thai con lai

Production golden parity va live model-service smoke van chua xac minh trong
checkout nay vi thieu endpoint, credential va production catalog thuc te.
