# Iteration 53 - Canonical image refs trong EvidenceBundle

## Phạm vi

Siết ranh giới retrieval -> chat theo yêu cầu `EvidenceBundle` phải chứa
validated image refs. Iteration này chỉ xử lý invariant của `image_refs`, không
thay đổi artifact gate hoặc cách trích xuất metadata.

## Thay đổi

- Từ chối image ref có khoảng trắng đầu/cuối.
- Từ chối image ref không ở dạng Unicode NFC canonical.
- Từ chối danh sách image refs có phần tử trùng nhau.
- Giữ nguyên yêu cầu kiểu container là `tuple` và phần tử không được blank.

Các kiểm tra được đặt trong domain DTO `EvidenceBundle`, nên mọi use case và
adapter tạo bundle đều dùng chung một contract trước khi dữ liệu đi vào chat.

## Bằng chứng kiểm thử

- TDD targeted: `uv run pytest tests/test_retrieve_evidence.py -q` -> **9 passed**.
- Full offline suite: `uv run pytest -q` -> **351 passed, 2 skipped, 1 warning**.
- Hai skip là do Gradio không cài và sample source không có; không liên quan
  tới thay đổi iteration này.

## Giới hạn xác minh

Chưa chạy live model-service smoke hoặc production golden parity vì checkout
chưa có endpoint, credential và catalog production được phê duyệt. Đây là
giới hạn môi trường, không phải bằng chứng cho hành vi live.
