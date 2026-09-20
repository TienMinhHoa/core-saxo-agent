# Bằng chứng Iteration 58 — canonical `insufficiency_reason`

## Phạm vi

Siết trường `EvidenceBundle.insufficiency_reason` tại ranh giới retrieval →
chat. Đây là lý do hiển thị khi không có evidence, nên phải là chuỗi không
trống và canonical giống các identity field khác.

## Thay đổi

- Từ chối reason không phải chuỗi, bao gồm `bool`, số và object tùy ý.
- Từ chối reason rỗng, có whitespace đầu/cuối hoặc Unicode chưa chuẩn NFC.
- Giữ nguyên invariant: evidence rỗng bắt buộc có reason; evidence có hit
  không được mang reason.
- Bổ sung regression tests theo TDD trong
  `tests/test_phase_5_retrieval_contract.py`.

## Bằng chứng kiểm thử

```text
uv run pytest tests/test_phase_5_retrieval_contract.py tests/test_retrieve_evidence.py -q
44 passed

uv run python -m compileall -q src tests
pass

git diff --check
pass (chỉ cảnh báo line-ending LF/CRLF của Git)
```

Live model-service smoke và production golden parity vẫn chưa thể xác minh vì
checkout chưa được cung cấp endpoint, credential và production catalog thật.
