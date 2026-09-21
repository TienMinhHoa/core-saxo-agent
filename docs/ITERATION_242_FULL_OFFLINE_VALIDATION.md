# Iteration 242 — Xác minh full offline sau Chroma factory cleanup

## Phạm vi

Iteration này hoàn tất phần xác minh còn thiếu sau iteration 241: chạy toàn bộ
offline test suite cho contract cleanup của Chroma factory. Không có endpoint,
credential model service hoặc production catalog trong checkout nên không tuyên
bố live smoke hay production parity.

## Thay đổi đã kế thừa

- Chroma factory đóng client khi constructor của `ChromaVectorIndex` thất bại,
  kể cả khi thao tác `client.close()` cũng ném lỗi.
- Lỗi gốc của constructor được giữ lại; lỗi cleanup không che khuất nguyên nhân
  ban đầu.

## Bằng chứng xác minh

Lệnh chạy:

```text
uv run pytest -q
```

Kết quả:

```text
925 passed, 18 skipped, 1 warning in 40.83s
```

Các test bị skip chỉ do môi trường Windows hiện tại không có Gradio, sample
source hoặc quyền tạo symbolic link (`WinError 1314`). Đây không phải test
failure.

Trạng thái live model-service smoke và production golden parity: **chưa xác
minh**, vì checkout vẫn thiếu endpoint, credential và production catalog thật.

