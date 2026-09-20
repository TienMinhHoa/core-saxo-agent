# Iteration 119 - Contract missing artifact

## Pham vi

Kiem tra su thong nhat giua `ArtifactRepository.get()` va adapter filesystem:
artifact khong ton tai phai tra `FileNotFoundError`; filesystem object khong phai
file van la loi identity rieng.

## Thay doi

- Them guard `path.exists()` trong `LocalArtifactRepository._read_file()` de
  phan biet artifact thieu voi directory collision.
- Them regression test cho missing artifact.

## Bang chung

- Targeted: `uv run pytest tests/test_phase_2_artifact_storage_contract.py -q`
- Full suite: `uv run pytest -q` -> **532 passed, 2 skipped, 1 warning**.
- `uv run python -m compileall -q src tests` -> dat.
- `git diff --check` -> dat.

## Ket luan

Contract read cua artifact immutable da phan biet ro missing identity va
destination sai loai, khong thay doi behavior tamper-check hay immutability.
