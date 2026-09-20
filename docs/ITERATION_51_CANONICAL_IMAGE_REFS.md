# Iteration 51 - canonical image references trong artifact gate

## Phạm vi

Tiếp tục siết exit criterion Phase 6: image reference phải là chuỗi canonical
trước khi được truyền sang answer generator. Gate trước đây đã chặn path tuyệt
đối, URL remote và traversal, nhưng vẫn có thể nhận reference có khoảng trắng
đầu/cuối hoặc dấu gạch chéo ngược rồi trả lại giá trị chưa chuẩn hóa.

## Thay đổi

- `SafeImageArtifactGate` từ chối reference nếu giá trị đầu vào khác giá trị
  canonical sau khi trim và đổi dấu `\\` sang `/`.
- Bổ sung contract test cho khoảng trắng đầu/cuối; test chứng minh gate không
  cho reference không canonical đi tiếp.

## Bằng chứng kiểm thử

- `uv run pytest tests/test_chat_answer_question.py -q`: **13 passed**.
- `uv run pytest -q`: **345 passed, 2 skipped, 1 warning**.
- `python -m compileall -q src tests`: đạt.
- `git diff --check`: đạt; chỉ có cảnh báo line ending CRLF của Git trên
  Windows, không có whitespace error.

## Trạng thái và giới hạn

Lát cắt canonical image reference đã hoàn tất ở chat boundary và không gây
regression trong offline suite. Hai test bị skip do Gradio/sample source không
có trong checkout. Live model-service smoke vẫn phụ thuộc endpoint, credential
và catalog thật chưa có trong checkout.
