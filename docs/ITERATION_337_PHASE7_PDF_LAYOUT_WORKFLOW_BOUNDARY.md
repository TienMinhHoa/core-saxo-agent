# Iteration 337 窶・Boundary workflow cho response layout PDF

## M盻･c tiﾃｪu

Ti蘯ｿp t盻･c Phase 7 c盻ｧa `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: HTTP interface ch盻・ﾄ訴盻「 ph盻訴 request/response, cﾃｲn workflow s盻・h盻ｯu vi盻㌘ ghﾃｩp state hoﾃn t蘯･t v盻嬖 cﾃ｡c trang layout.

## Thay ﾄ黛ｻ品

- Thﾃｪm `load_layout_pages()` vﾃo public workflow facade.
- Hﾃm workflow nh蘯ｭn cﾃ｡c policy qua dependency injection: ki盻ノ tra job ﾄ妥｣ hoﾃn t蘯･t, projection state, ﾄ柁ｰ盻拵g d蘯ｫn layout vﾃ b盻・ﾄ黛ｻ皇 layout.
- Route `GET /api/jobs/{job_id}/layout` ch盻・g盻絞 workflow vﾃ map l盻擁 sang HTTP 404/409; khﾃｴng cﾃｲn t盻ｱ ghﾃｩp payload layout.
- Thﾃｪm unit/AST contract test ﾄ黛ｻ・khﾃｳa boundary vﾃ th盻ｩ t盻ｱ g盻絞 policy.

## B蘯ｱng ch盻ｩng ki盻ノ tra

- Targeted: `uv run pytest tests/test_phase_7_pdf_layout_wrapper.py -q` — 33 passed.
- Full offline: `uv run pytest -q` — 1056 passed, 18 skipped, 1 warning.
- Ki盻ノ tra cﾃｺ phﾃ｡p: `uv run python -m compileall -q src tests`.
- Live model-service smoke vﾃ production parity chﾆｰa ch蘯｡y vﾃｬ checkout chﾆｰa cﾃｳ endpoint, credential vﾃ catalog production ﾄ柁ｰ盻｣c phﾃｪ duy盻㏄.

## Tr蘯｡ng thﾃ｡i

Slice nﾃy hoﾃn t蘯･t boundary cleanup cho layout response. Stop condition toﾃn b盻・architecture plan chﾆｰa ﾄ柁ｰ盻｣c ﾄ妥｡nh d蘯･u hoﾃn t蘯･t vﾃｬ live smoke/parity vﾃ cﾃ｡c exit criteria cﾃｲn l蘯｡i c蘯ｧn ﾄ柁ｰ盻｣c xﾃ｡c minh riﾃｪng.
