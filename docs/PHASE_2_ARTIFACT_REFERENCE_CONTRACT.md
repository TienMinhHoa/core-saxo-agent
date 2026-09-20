# Phase 2 - hợp đồng artifact reference

## Mục tiêu lát cắt

Tiếp tục Phase 2 của `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md` bằng một
domain contract nhỏ cho artifact immutable/versioned. Hợp đồng này giúp các
use case truyền metadata của PDF, Markdown, layout, ảnh và manifest mà không
để lộ đường dẫn filesystem vào application layer.

## Thay đổi

- Tạo `saxophone.documents.models.ArtifactKind` cho các loại artifact cốt lõi.
- Tạo `ArtifactRef` bất biến với identity, version, media type, SHA-256 và kích
  thước byte.
- Validate ngay tại boundary: identifier/version/media type không rỗng, digest
  là lowercase SHA-256 64 ký tự và kích thước không âm.
- Chưa tạo storage adapter; việc ánh xạ reference sang filesystem/remote
  transfer sẽ là lát cắt riêng để tránh trộn domain contract với I/O.

## Bằng chứng kiểm chứng

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_phase_2_artifact_reference_contract.py --basetemp=.pytest-tmp
```

Kết quả: contract test của lát cắt này đạt **7 passed**.

Lát cắt này chưa chứng minh persistence, atomic write hay remote artifact
transfer. Đây là giới hạn có chủ ý; các adapter đó vẫn là công việc Phase 2
tiếp theo.
