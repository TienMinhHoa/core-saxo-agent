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

### Cap nhat iteration 25 - route process tai lieu

- Them `POST /api/v1/documents/{document_ref}/process` trong inbound adapter.
- Request chi nhan metadata `ArtifactRef` cua PDF nguon, phien ban nguon,
  correlation id va model profile; route khong nhan local filesystem path.
- Route tao `PdfExtractionRequest`, goi `PdfExtractor` da duoc composition root
  inject, sau do tra ve cac artifact typed `markdown`, `layout`, `manifest` va
  coordinates. Provider/model SDK van nam ngoai API adapter.
- Test API dung fake extractor de xac minh route delegate dung document ref,
  correlation id va khong goi remote transport; khong co live model-service
  smoke trong iteration nay.

Bang chung bo sung:

- `uv run pytest tests/test_phase_7_api_routes.py tests/test_phase_1_composition_root.py tests/test_phase_3_remote_pdf_extractor.py --basetemp=.pytest-tmp`
  dat sau khi implementation hoan tat.
- Route nay moi chi la processing boundary; chua persist artifact, upload
  streaming, ingest/index, hay tra trang thai indexed. Cac buoc do van can
  workflow va repository contract rieng.

Ranh gioi con lai:

Chua co upload endpoint, document processing workflow day du, artifact commit,
hoac ingestion wiring. Cac viec nay can contract rieng de tranh tron logic vao
composition root.
