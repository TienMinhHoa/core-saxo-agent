# Iteration 341 - dọn metadata package legacy OCR

## Phạm vi

Phase 7 yêu cầu loại bỏ wrapper/file cũ đã hết dùng và không kéo runtime GPU
local vào backend. Sau Iteration 340, provider `extracted.parse_pdf_2_md` chỉ còn
được tham chiếu trong adapter tương thích có chủ đích; tuy nhiên cấu hình
setuptools vẫn khai báo package pattern `extracted*`. Đây là metadata đã lỗi
thời, có thể làm distribution tiếp tục quảng bá một package không còn nằm
trong source tree.

## Thay đổi

- Xóa `extracted*` khỏi `tool.setuptools.packages.find.include` trong
  `pyproject.toml`; package backend chỉ còn `music_rag*` và `saxophone*`.
- Thêm dependency-enforcement test để ngăn metadata legacy quay lại.

## Bằng chứng kiểm tra

- Red test trước thay đổi: test mới fail vì `pyproject.toml` còn chứa
  `include = ["music_rag*", "extracted*", "saxophone*"]`.
- Targeted test sau thay đổi: sẽ chạy cùng full suite ở cuối iteration.
- Live model-service smoke và production parity vẫn chưa xác minh vì checkout
  không có endpoint, credential và production catalog được phê duyệt.
