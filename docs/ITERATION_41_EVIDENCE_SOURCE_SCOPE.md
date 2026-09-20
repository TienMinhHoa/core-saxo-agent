# Iteration 41 — Giới hạn source text tại evidence boundary

## Mục tiêu

Tiếp tục lựa chọn Clean Code: `EvidenceBundle` chỉ cho phép chuyển source text
của các `selected_refs` đã được retrieval chọn và validate. Dữ liệu source dư,
không được chọn, không được phép đi tiếp sang chat/model adapter.

## Thay đổi

- Bổ sung invariant `set(source_texts) == set(selected_refs)` trong
  `src/saxophone/retrieval/models.py`.
- Bổ sung regression test chứng minh source text có key ngoài selected refs bị
  từ chối.

## Bằng chứng kiểm thử

- `uv run pytest tests/test_retrieve_evidence.py -q`: **5 passed**.
- Chưa chạy live model-service smoke: checkout vẫn không có endpoint/credential
  production được cấp để kiểm chứng.

## Tác động kiến trúc

Contract này củng cố quy tắc trong Solution Architecture: answer generator chỉ
được nhận evidence đã validate, không được tự truy vấn database hoặc nhận thêm
nguồn ngoài bundle.
