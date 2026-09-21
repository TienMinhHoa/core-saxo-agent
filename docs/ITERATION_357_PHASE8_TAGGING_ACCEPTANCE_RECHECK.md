# Iteration 357 - tái kiểm chứng Phase 8: paragraph tagging trong ingestion

## Phạm vi

Tái kiểm chứng lát cắt paragraph tagging theo `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`
và `TOPIC_TAGGING_PLAN.md`, không thay đổi runtime code. Phạm vi gồm parser
deterministic, contract của tag generator/conflict resolver, persistence sidecar,
và việc coordinator ingestion đưa tag vào projection index.

## Bằng chứng kiểm thử

Đã chạy:

```text
uv run pytest tests/test_phase_8_*.py --basetemp=.pytest-tmp-357-phase8
```

Kết quả: **31 passed, 2 skipped** trong 33 test. Hai test bị skip vì môi trường
Windows hiện tại không cung cấp symbolic link; đây là giới hạn môi trường, không
phải lỗi contract.

Các contract đã được xác minh:

- paragraph giữ nguyên `paragraph_id`, `chunk_id`, thứ tự và source text;
- tag là chuỗi tiếng Anh, không có business/ontology ID;
- output sai task hoặc sai schema của model bị từ chối;
- conflict resolution chỉ giữ tag mới hoặc tái sử dụng candidate hợp lệ;
- persistence sidecar và tag catalog có tính thay thế, deterministic, atomic;
- lỗi persistence không bị nuốt;
- ingestion coordinator truyền tag vào metadata chunk để retrieval có thể mở rộng
  qua `ChunkRetriever` mà không sửa chat use case.

## Trạng thái nghiệm thu

Lát cắt Phase 8 đạt offline. Chưa thể xác minh live model-service smoke hoặc
production parity vì checkout không có endpoint, credential và catalog production
được phê duyệt. Vì vậy chưa đánh dấu toàn bộ architecture plan là production-ready.
