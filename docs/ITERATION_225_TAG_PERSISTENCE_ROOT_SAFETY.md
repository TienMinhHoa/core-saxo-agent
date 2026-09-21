# Iteration 225 - file-safety cho tag persistence

## Phạm vi

Đóng gap nhỏ trong `saxophone.tagging.persistence`: JSON sidecar và tag catalog
không được đi qua symbolic-link path, kể cả khi path bị thay đổi sau khi
repository được khởi tạo.

## Thay đổi

- `JsonTaggedParagraphRepository` kiểm tra kiểu root, reject root là file,
  reject symbolic-link component trước và sau khi tạo thư mục, và kiểm tra lại
  root trước khi dựng sidecar path.
- `JsonTagCatalogRepository` giữ path tuyệt đối theo lexical components để có
  thể phát hiện parent bị redirect, reject catalog là directory, và re-check
  path trong các thao tác đọc/ghi.
- Bổ sung regression tests cho root là file, root bị thay bằng symbolic link,
  và catalog parent là symbolic link. Môi trường Windows không cấp quyền tạo
  symbolic link nên hai case tương ứng được skip có kiểm soát.

## Bằng chứng kiểm thử

- `uv run pytest tests/test_phase_8_tag_persistence_ports.py -q
  --basetemp=.pytest-tmp-tag-safety`: **8 passed, 2 skipped**.
- Hai skip là giới hạn quyền symbolic link của môi trường; contract vẫn được
  giữ trong test và sẽ chạy khi môi trường có quyền tạo link.
- Full suite: **912 passed, 8 skipped, 1 warning** trong 37.07 giây.
- `python -m compileall -q src tests` và `git diff --check` đều thành công.

## Trạng thái còn lại

Live model-service smoke và production golden parity vẫn chưa xác minh vì
checkout chưa có endpoint, credential và production catalog thật.
