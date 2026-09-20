# Bằng chứng Iteration 57 — contract số của ChunkHit

## Phạm vi

Siết validation tại ranh giới retrieval DTO `ChunkHit`. Python coi `bool` là một
nhánh con của `int`, vì vậy `True` trước đây có thể lọt vào `rank`, còn
`math.isfinite(True)` có thể coi `True` là score hợp lệ. Điều này làm yếu typed
result validation trước khi evidence đi sang chat.

## Thay đổi

- `rank` phải là `int` thật, không phải `bool`, và phải từ 1 trở lên.
- `semantic_score`, `keyword_score`, `fused_score` phải là số `int`/`float`
  thật, không phải `bool`, đồng thời phải hữu hạn.
- Bổ sung regression test TDD cho boolean rank và boolean semantic score.

## Bằng chứng kiểm thử

Đã chạy trong checkout này:

```text
uv run pytest tests/test_phase_5_retrieval_contract.py tests/test_retrieve_evidence.py -q
37 passed

python -m compileall -q src tests
pass

git diff --check
pass (chỉ có cảnh báo line-ending LF/CRLF của Git)
```

## Trạng thái và giới hạn

Slice này đạt contract offline cho numeric DTO và không thay đổi transport,
storage hay API shape. Live model-service smoke và production golden parity vẫn
chưa xác minh vì checkout chưa có endpoint, credential và production catalog
được cung cấp.
