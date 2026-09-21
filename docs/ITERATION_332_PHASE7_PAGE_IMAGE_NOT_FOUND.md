# Iteration 332 - map job PDF khong ton tai khi lay anh trang

## Pham vi

Kiem tra route `GET /api/jobs/{job_id}/pages/{page_number}` sau slice
Iteration 331. Khi `job_id` khong phai UUID hop le, `page_image_path()` cua
`PdfLayoutJobStore` nem `PdfLayoutJobNotFound`; neu route khong map loi nay,
FastAPI se tra 500 thay vi 404.

## Thay doi

- Route page-image map ca `PdfLayoutJobNotFound` va `ValueError` thanh HTTP
  404, giu nguyen thong diep loi tong quat va khong lo path noi bo.
- Them regression contract test de khoa hanh vi 404 cho job khong ton tai.

## Bang chung

- Targeted: `uv run pytest -q tests/test_phase_7_pdf_layout_wrapper.py -k
  "page_route or page_image or layout_missing"` -> `3 passed, 24 deselected`.
- Chua chay full suite trong iteration nay; can chay lai truoc khi ket luan
  toan bo acceptance.
- Live model-service smoke va production parity van chua xac minh do checkout
  thieu endpoint, credential va production catalog.

## Ket luan

Slice nay dong nhat error boundary cua PDF page-image voi cac route PDF khac:
job khong ton tai hoac identifier khong hop le deu duoc tra ve 404.
