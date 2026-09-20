# Evidence Phase 1: composition retrieval và chat

## Phạm vi

Lát cắt này hoàn thiện một phần composition root theo lựa chọn Clean Code: application
container có thể dựng retrieval và chat từ các application port, còn FastAPI route không
biết trực tiếp SDK/provider. Khi thiếu port bắt buộc, capability vẫn ở trạng thái
`disabled` thay vì tạo fallback giả.

## Thay đổi

- `AppOverrides` nhận `ChunkRetriever`, `AnswerGenerator` và `ImageArtifactGate`.
- `create_app()` dựng `RetrieveEvidence` khi có retriever, sau đó dựng `AnswerQuestion`
  khi có answer generator.
- `AppContainer` và health response nhận đúng các use case đã compose.
- `saxophone.main` dùng lazy proxy cho `uvicorn`, tránh side effect khi import module
  nhưng vẫn giữ seam `uvicorn.run` cho CLI test.

## Bằng chứng kiểm tra

Đã chạy trong repository:

```text
uv run pytest -q
266 passed, 2 skipped, 1 warning

uv run python -m compileall -q src
pass

git diff --check
pass
```

Test mới xác nhận `retrieval` và `chat` chuyển sang `ready` khi composition root được
cấp các port ứng dụng tương ứng. Hai test skip là do môi trường thiếu Gradio và fixture
sample source; không phải regression của lát cắt này.

## Giới hạn còn lại

Lát cắt này chưa tự khởi tạo Chroma collection/remote retrieval production từ settings;
đó là bước composition infrastructure tiếp theo. Không có live model-service hoặc
Chroma smoke test trong iteration này.
