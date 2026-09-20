# Iteration 117 - fail-closed khi artifact path khong phai file

## Pham vi

Clean Code tiep tuc cung co boundary cua `LocalArtifactRepository`. Neu
`artifact_id/version` da ton tai nhung la mot thu muc, repository khong duoc
co gang doc no nhu payload hoac de exception filesystem tuy y thoat ra. Identity
artifact la immutable, vi vay moi path da ton tai nhung khong phai file deu bi
tu choi bang `FileExistsError`.

## Thay doi

- Them guard `path.is_file()` ngay sau existence-check va truoc khi doc payload.
- Bo sung regression test xac minh thu muc tai artifact path khong bi ghi de,
  khong tao file tam, va tra ve loi immutable nhat quan.

## Bang chung kiem tra

- Targeted: `uv run pytest tests/test_phase_2_artifact_storage_contract.py`
- Full suite: chay lai `uv run pytest` sau khi targeted xanh.
- Quality: `uv run python -m compileall -q src tests` va `git diff --check`.
- Live model-service smoke va production golden parity van chua the xac minh
  vi checkout chua co endpoint, credential va catalog production.
