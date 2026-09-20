# Iteration 46 - ChatResult khong cho phep metadata khi thieu evidence

## Pham vi

Khoa mot khe hở nho trong contract `ChatResult`: response co trang thai
`INSUFFICIENT_EVIDENCE` phai la response an toan, khong duoc mang theo metadata
cua provider (vi du `model_version`). Use case hien tai khong goi LLM khi khong
co hit, nen metadata nay neu xuat hien se tao contract khong nhat quan.

## Thay doi

- Them invariant vao `src/saxophone/chat/models.py`: ket qua thieu evidence
  khong duoc co `model_version`, ben canh cac truong answer, evidence ref va
  citations da bi cam.
- Them regression test TDD vao `tests/test_chat_answer_question.py` cho
  `model_version` bi tu choi trong trang thai thieu evidence.

## Bang chung kiem tra

- Targeted: `uv run pytest tests/test_chat_answer_question.py` - dat.
- Full suite: `342 passed, 2 skipped, 1 warning`.
- Static checks: `uv run python -m compileall -q src tests` va `git diff --check` deu dat.

## Gioi han xac minh

Slice nay chi xac minh contract offline. Live model-service smoke va golden
parity production van chua the chay do checkout chua co endpoint, credential va
production catalog that.
