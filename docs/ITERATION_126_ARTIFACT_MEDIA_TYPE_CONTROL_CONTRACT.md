# Iteration 126 - Chặn control character trong MIME của artifact

## Phạm vi

Iteration này tiếp tục hardening `ArtifactRef` theo phần Security và file
safety của `docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`. MIME type được giữ
trong metadata và có thể đi qua API; vì vậy cả phần type/subtype lẫn parameter
phải không chứa control character.

## Thay đổi

- `is_safe_media_type()` fail-closed với mọi ký tự `< 0x20` và `DEL` (`0x7f`)
  trong toàn bộ chuỗi MIME, không chỉ trong type/subtype.
- Bổ sung regression tests cho tab, newline và `DEL` trong MIME parameter.
- Không thay đổi MIME parameter hợp lệ như `application/json; charset=utf-8`.

## Kiểm chứng

```text
uv run pytest tests/test_phase_2_artifact_reference_contract.py -q
```

Kết quả: **44 passed**. Đây là kiểm chứng offline; live model-service smoke
và production golden parity vẫn chưa thể chạy vì checkout chưa có endpoint,
credential và catalog production được phê duyệt.
