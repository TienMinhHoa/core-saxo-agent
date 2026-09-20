# Phase 3 - Wiring PdfExtractor vao composition root

## Pham vi iteration 24

Theo huong Clean Code, iteration nay noi `PdfExtractor` vao `AppContainer` ma
khong dua FastAPI, HTTP client hay provider SDK vao extraction module.

## Thay doi

- `create_app()` mac dinh tao `RemotePdfExtractor` tu `ModelClient` da duoc
  compose, dung `SAXO_LITELLM_MODEL_PROFILE` lam model profile.
- `AppOverrides.pdf_extractor` cho phep test thay the extractor bang fake ma
  khong goi model service.
- Health endpoint bao `extraction=ready` khi extractor da duoc compose.
- Them property chi doc `RemotePdfExtractor.model` de kiem chung cau hinh ma
  khong lo transport noi bo.

## Bang chung kiem thu

- `uv run pytest tests/test_phase_1_composition_root.py tests/test_phase_3_remote_pdf_extractor.py --basetemp=.pytest-tmp`: dat.
- Test moi bao gom default wiring va override wiring; test override xac nhan
  health extraction ready ma khong can remote service.

## Ranh gioi con lai

Chua co HTTP extraction route, document processing workflow, artifact commit,
hoac ingestion wiring. Cac viec nay can contract rieng de tranh tron logic vao
composition root.
