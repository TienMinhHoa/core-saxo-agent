# Phase 7 - B盻・sung bounded limiter cho Chroma search

## K蘯ｿt qu蘯｣

Phﾃ｡t hi盻㌻ `ChromaVectorIndex.search()` chﾆｰa truy盻］ `self._io_limiter`
khi g盻絞 `anyio.to_thread.run_sync`. ﾄ妥｣ b盻・sung `limiter=` vﾃo call query,
ﾄ黛ｺ｣m b蘯｣o `get`, `upsert`, `delete` vﾃ `query` dﾃｹng chung capacity limiter
cho blocking Chroma I/O.

## TDD vﾃ b蘯ｱng ch盻ｩng

- Thﾃｪm contract test `test_chroma_search_passes_shared_blocking_io_limiter`;
  test ﾄ妥ｳ fail trﾆｰ盻嫩 khi `search` b盻・quﾃｪn limiter.
- Sau khi s蘯ｽa: targeted test pass, cﾃng v盻嬖 nhﾃｳm bounded-I/O vﾃ full suite.
- Khﾃｴng ch蘯｡y live Chroma ho蘯ｷc production multi-worker smoke trong slice nﾃy.
