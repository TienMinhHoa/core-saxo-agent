# Phase 1 - Vòng đời Chroma do composition root sở hữu

## Phạm vi

Lát cắt này làm rõ ownership của `PersistentClient`: factory truyền client vào
`ChromaVectorIndex`, còn FastAPI lifespan giải phóng client khi application
shutdown. Điều này giữ cleanup ở composition root và tránh để route/use case
phụ thuộc trực tiếp vào SDK Chroma.

## Thay đổi

- `ChromaVectorIndex` có hook `close()` tùy chọn, không làm thay đổi
  `VectorIndex` application port.
- `create_chroma_vector_index` giữ client cùng adapter để client không bị
  garbage-collect sớm và có thể được đóng có chủ đích.
- `create_app` gọi cleanup cho vector index trước khi đóng HTTP client.
- Thêm regression test chứng minh client Chroma được đóng sau ASGI lifespan.

## Bằng chứng kiểm thử

```text
uv run pytest -q tests/test_phase_1_composition_root.py tests/test_phase_1_chroma_live_contract.py --basetemp=.pytest-tmp/iter96
22 passed

python -m compileall -q src tests
pass

git diff --check
pass
```

## Giới hạn

Đã xác minh lifecycle offline với Chroma thật ở test persistent và fake client
ở composition test. Chưa xác minh shutdown của một deployment multi-worker
hoặc model service bên ngoài máy test.
