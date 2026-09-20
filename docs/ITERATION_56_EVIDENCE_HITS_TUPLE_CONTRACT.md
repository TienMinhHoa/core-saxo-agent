# Iteration 56 - hop hits bat bien tai boundary retrieval-chat

## Muc tieu

Tiep tuc Clean Code cho `EvidenceBundle`: tap `hits` la du lieu DTO da duoc
validate, nen khong duoc de list mutable hoac phan tu sai kieu vuot qua ranh
gioi retrieval -> chat.

## Thay doi

- `EvidenceBundle` tu choi `hits` neu khong phai `tuple`.
- `EvidenceBundle` tu choi moi phan tu khong phai `ChunkHit`.
- Bo sung test regression cho ca list mutable va phan tu sai kieu.

## Bang chung

- Targeted: `uv run pytest tests/test_retrieve_evidence.py` - dat.
- Full suite: `uv run pytest` - dat.
- Static: `uv run python -m compileall -q src tests` - dat.
- Hygiene: `git diff --check` - dat.

## Gioi han xac minh

Day la bang chung offline. Live model-service smoke va production golden
parity van chua chay vi checkout chua co endpoint, credential va catalog
production duoc phe duyet.
