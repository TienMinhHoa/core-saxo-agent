#!/usr/bin/env python3
"""Local web backend for extracting and visually reviewing PDF layouts.

Run with:
    uv run pdf-layout-web --host 127.0.0.1 --port 8000

The browser uploads a PDF, starts a background PP-StructureV3 extraction job,
then renders the source page with normalized layout boxes beside the extracted
text/image blocks.  All files remain local under ``runtime/pdf-layout-jobs``.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import threading
import uuid
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from saxophone.extraction import read_layout_pages
from saxophone.workflows import run_extraction
from saxophone.workflows.pdf_layout_jobs import PdfLayoutJobNotFound, PdfLayoutJobStore


PROJECT_DIR = Path(__file__).resolve().parents[3]
JOBS_DIR = PROJECT_DIR / "runtime" / "pdf-layout-jobs"
MAX_UPLOAD_BYTES = 200 * 1024 * 1024
EXTRACTION_LOCK = threading.Lock()
JOB_STORE = PdfLayoutJobStore(JOBS_DIR)

app = FastAPI(title="PDF Layout Extractor", docs_url=None, redoc_url=None)


def _job_dir(job_id: str) -> Path:
    """Resolve a UUID-backed job directory without accepting path traversal."""
    try:
        uuid.UUID(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Job không tồn tại") from exc
    return JOB_STORE.job_dir(job_id)


def _load_state(job_id: str) -> dict[str, Any]:
    try:
        return JOB_STORE.load_state(job_id)
    except PdfLayoutJobNotFound as exc:
        raise HTTPException(status_code=404, detail="Job khﾃｴng t盻渡 t蘯｡i") from exc
    except (OSError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=404, detail="Job không tồn tại") from exc


def _write_state(job_id: str, state: dict[str, Any]) -> None:
    """Atomically update job state so polling never reads partial JSON."""
    JOB_STORE.write_state(job_id, state)


def _timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


async def _save_upload(upload: UploadFile, destination: Path) -> int:
    """Write an upload with a bounded size; never trust its client filename."""
    bytes_written = 0
    try:
        with destination.open("wb") as handle:
            while chunk := await upload.read(1024 * 1024):
                bytes_written += len(chunk)
                if bytes_written > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"PDF vượt giới hạn {MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
                    )
                handle.write(chunk)
    finally:
        await upload.close()
    return bytes_written


def _page_number(path: Path) -> int:
    match = re.search(r"-(\d+)\.png$", path.name)
    return int(match.group(1)) if match else 0


def _render_pages(source_pdf: Path, page_dir: Path) -> list[str]:
    """Rasterize PDF pages locally for an overlay-friendly browser viewer."""
    if shutil.which("pdftoppm") is None:
        raise RuntimeError("Thiếu lệnh pdftoppm. Cài poppler-utils để render trang PDF.")
    page_dir.mkdir(parents=True, exist_ok=True)
    prefix = page_dir / "page"
    subprocess.run(
        ["pdftoppm", "-png", "-r", "144", str(source_pdf), str(prefix)],
        check=True,
        capture_output=True,
        text=True,
    )
    return [path.name for path in sorted(page_dir.glob("page-*.png"), key=_page_number)]


@app.get("/", response_class=HTMLResponse)
def home() -> HTMLResponse:
    # The viewer is a single inline HTML/JS asset; never leave an old client
    # with a cached UI after a backend deployment.
    return HTMLResponse(VIEWER_HTML, headers={"Cache-Control": "no-store"})


@app.post("/api/jobs")
async def create_job(file: UploadFile = File(...)) -> dict[str, Any]:
    supplied_name = Path(file.filename or "document.pdf").name
    if not supplied_name.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Chỉ nhận file PDF")
    job_id = str(uuid.uuid4())
    job_dir = _job_dir(job_id)
    job_dir.mkdir(parents=True, exist_ok=False)
    try:
        size = await _save_upload(file, job_dir / "source.pdf")
        if size == 0:
            raise HTTPException(status_code=400, detail="PDF rỗng")
        state = {
            "id": job_id,
            "original_filename": supplied_name,
            "status": "uploaded",
            "created_at": _timestamp(),
            "started_at": None,
            "finished_at": None,
            "device": None,
            "language": None,
            "page_count": None,
            "phase": "uploaded",
            "progress_pages": 0,
            "progress_total": None,
            "progress_images": 0,
            "error": None,
        }
        _write_state(job_id, state)
        return JOB_STORE.public_state(state)
    except Exception:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise


@app.post("/api/jobs/{job_id}/extract")
def start_extraction(job_id: str, device: str = "cpu", language: str = "vi") -> dict[str, Any]:
    state = _load_state(job_id)
    if state.get("status") not in {"uploaded", "failed"}:
        raise HTTPException(status_code=409, detail="Job này đã hoặc đang được xử lý")
    device = device.strip().lower()
    if device != "cpu" and not re.fullmatch(r"gpu(?::\d+)?", device):
        raise HTTPException(status_code=400, detail="device phải là cpu, gpu hoặc gpu:<số>")
    language = language.strip().lower()
    if not re.fullmatch(r"[a-z_]{2,20}", language):
        raise HTTPException(status_code=400, detail="Mã ngôn ngữ không hợp lệ")
    state.update(
        {
            "status": "queued",
            "device": device,
            "language": language,
            "phase": "queued",
            "progress_pages": 0,
            "progress_total": None,
            "progress_images": 0,
            "error": None,
        }
    )
    _write_state(job_id, state)
    threading.Thread(
        target=run_extraction,
        args=(job_id,),
        kwargs={
            "job_dir": _job_dir,
            "load_state": _load_state,
            "write_state": _write_state,
            "render_pages": _render_pages,
            "extraction_lock": EXTRACTION_LOCK,
        },
        daemon=True,
    ).start()
    return JOB_STORE.public_state(state)


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> dict[str, Any]:
    return JOB_STORE.public_state(_load_state(job_id))


@app.get("/api/jobs/{job_id}/layout")
def job_layout(job_id: str) -> dict[str, Any]:
    state = _load_state(job_id)
    if state.get("status") != "completed":
        raise HTTPException(status_code=409, detail="Kết quả chưa sẵn sàng")
    layout_dir = _job_dir(job_id) / "extraction" / "source" / "layout"
    return {
        "job": JOB_STORE.public_state(state),
        "pages": read_layout_pages(
            layout_dir, lambda page: f"/api/jobs/{job_id}/pages/{page}"
        ),
    }


@app.get("/api/jobs/{job_id}/pages/{page_number}")
def page_image(job_id: str, page_number: int) -> FileResponse:
    if page_number < 1:
        raise HTTPException(status_code=404, detail="Trang không tồn tại")
    candidate = _job_dir(job_id) / "pages" / f"page-{page_number}.png"
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="Trang không tồn tại")
    return FileResponse(candidate, media_type="image/png")


VIEWER_HTML = r"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PDF Layout Extractor</title>
  <style>
    :root { color-scheme: light; font-family: Inter, ui-sans-serif, system-ui, sans-serif; background:#f4f7fb; color:#172033; }
    * { box-sizing:border-box; } body { margin:0; } button, select, input { font:inherit; }
    header { padding:18px max(24px, calc((100vw - 1460px)/2)); background:#111b31; color:white; display:flex; align-items:center; gap:18px; }
    header h1 { margin:0; font-size:20px; } header p { margin:0; color:#b7c7e6; font-size:14px; }
    main { max-width:1460px; margin:0 auto; padding:24px; }
    .controls { background:white; padding:18px; border-radius:12px; display:flex; gap:12px; align-items:end; box-shadow:0 2px 12px #15204010; }
    label { display:grid; gap:6px; font-size:13px; font-weight:600; color:#4a5871; } input[type=file], select { max-width:320px; padding:8px; border:1px solid #cbd5e1; border-radius:7px; background:white; }
    button { padding:9px 14px; border:0; border-radius:7px; background:#2167d5; color:white; font-weight:700; cursor:pointer; } button:disabled { background:#9aabc7; cursor:not-allowed; }
    #status { min-height:25px; margin:14px 2px 8px; color:#465775; } #status.error { color:#b42318; }
    #progress { display:grid; grid-template-columns:minmax(120px, 1fr) auto; gap:10px; align-items:center; margin:0 2px 14px; color:#52637e; font-size:13px; } #progress[hidden] { display:none; }
    .progress-track { height:9px; overflow:hidden; border-radius:99px; background:#dce5f2; } #progress-fill { width:0; height:100%; border-radius:inherit; background:linear-gradient(90deg,#2167d5,#4e9cff); transition:width .35s ease; }
    #viewer { display:grid; grid-template-columns: minmax(250px, .8fr) minmax(400px, 1.75fr) minmax(300px, 1fr); gap:16px; height:calc(100vh - 182px); min-height:560px; }
    .panel { background:white; border-radius:12px; box-shadow:0 2px 12px #15204010; overflow:auto; }
    .panel-title { margin:0; padding:14px 16px; position:sticky; top:0; z-index:2; background:white; border-bottom:1px solid #e5eaf2; font-size:14px; }
    #pages { padding:8px; } .page-button { width:100%; text-align:left; color:#23334f; background:white; border:1px solid transparent; margin:2px 0; font-weight:500; }
    .page-button:hover, .page-button.active { background:#eaf2ff; border-color:#a9c7fb; color:#13499e; }
    #canvas-panel { background:#e9edf4; display:flex; flex-direction:column; align-items:center; overflow:auto; padding:20px; }
    #page-wrap { position:relative; width:min(100%, 860px); line-height:0; box-shadow:0 4px 22px #0003; margin:auto; } #page-wrap img { display:block; width:100%; height:auto; }
    .box { position:absolute; border:2px solid #ed8b00; background:#ed8b001c; cursor:pointer; line-height:normal; } .box:hover, .box.active { border-color:#d61f69; background:#d61f6930; }
    .box span { display:none; position:absolute; top:-20px; left:-2px; background:#d61f69; color:white; font:11px/16px ui-sans-serif; white-space:nowrap; padding:0 4px; border-radius:3px; } .box:hover span, .box.active span { display:block; }
    #blocks { padding:8px; } .block { border:1px solid #e1e7f0; border-radius:8px; padding:11px; margin:8px 0; cursor:pointer; } .block:hover, .block.active { border-color:#d61f69; box-shadow:0 0 0 2px #d61f6922; }
    .meta { font-size:12px; font-weight:700; color:#5c6d89; text-transform:uppercase; margin-bottom:6px; } .text { white-space:pre-wrap; overflow-wrap:anywhere; line-height:1.42; font-size:14px; } .empty { color:#71809a; padding:16px; line-height:1.5; }
    .crop { width:100%; overflow:hidden; position:relative; background:#eef2f7; margin-top:8px; border-radius:5px; } .crop img { position:absolute; max-width:none; }
    @media (max-width:980px) { #viewer { grid-template-columns:180px 1fr; height:auto; } #right-panel { grid-column:1 / -1; max-height:45vh; } #canvas-panel { min-height:560px; } }
    @media (max-width:620px) { main { padding:12px; } header { padding:14px; display:block; } header p { margin-top:5px; } .controls { display:grid; align-items:stretch; } #viewer { display:block; } .panel { margin:12px 0; min-height:260px; } #canvas-panel { min-height:400px; } }
  </style>
</head>
<body>
  <header><h1>PDF Layout Extractor</h1><p>PDF → OCR/layout → kiểm tra bounding box và nội dung trích xuất</p></header>
  <main>
    <section class="controls">
      <label>PDF<input id="file" type="file" accept="application/pdf,.pdf"></label>
      <label>Thiết bị<select id="device"><option value="cpu">CPU</option><option value="gpu:0">GPU 0</option><option value="gpu:1">GPU 1</option><option value="gpu:2">GPU 2</option><option value="gpu:3">GPU 3</option></select></label>
      <label>Ngôn ngữ OCR<select id="language"><option value="vi">Tiếng Việt</option><option value="en">English</option></select></label>
      <button id="upload">1. Thêm tài liệu</button><button id="extract" disabled>2. Chạy extract</button>
    </section>
    <p id="status">Chọn một PDF, sau đó thêm tài liệu.</p>
    <div id="progress" hidden><div class="progress-track"><div id="progress-fill"></div></div><span id="progress-label"></span></div>
    <section id="viewer" hidden>
      <aside class="panel"><h2 class="panel-title">Trang PDF</h2><div id="pages"></div></aside>
      <section id="canvas-panel" class="panel"><div id="page-wrap"></div></section>
      <aside id="right-panel" class="panel"><h2 class="panel-title">Nội dung đã trích xuất</h2><div id="blocks"></div></aside>
    </section>
  </main>
  <script>
    const byId = id => document.getElementById(id);
    const state = { job: null, pages: [], selectedPage: 0, selectedBlock: null, poll: null };
    const status = (text, error=false) => { const el=byId('status'); el.textContent=text; el.className=error ? 'error' : ''; };
    function renderProgress(job) { const wrap=byId('progress'), fill=byId('progress-fill'), label=byId('progress-label'); const active=job && ['queued','running'].includes(job.status); if (!active) { wrap.hidden=true; return; } wrap.hidden=false; const done=Number(job.progress_pages)||0, total=Number(job.progress_total)||0; if (total>0) { const percent=Math.min(100, Math.round(done*100/total)); fill.style.width=`${percent}%`; label.textContent=`${done}/${total} trang · ${percent}%`; } else { fill.style.width='12%'; label.textContent=job.phase==='initializing' ? 'Đang khởi tạo model…' : 'Đang chờ…'; } }
    async function request(url, options) { const response = await fetch(url, options); const data = await response.json().catch(() => ({})); if (!response.ok) throw new Error(data.detail || 'Yêu cầu thất bại'); return data; }
    byId('upload').onclick = async () => {
      const file = byId('file').files[0]; if (!file) return status('Hãy chọn một file PDF.', true);
      byId('upload').disabled = true; byId('extract').disabled = true; status('Đang tải PDF lên…');
      try { const form = new FormData(); form.append('file', file); state.job = await request('/api/jobs', {method:'POST', body:form}); renderProgress(state.job); byId('extract').disabled=false; status(`Đã thêm ${state.job.original_filename}. Bấm “Chạy extract”.`); }
      catch (error) { status(error.message, true); }
      finally { byId('upload').disabled=false; }
    };
    byId('extract').onclick = async () => {
      if (!state.job) return; byId('extract').disabled=true;
      try { state.job = await request(`/api/jobs/${state.job.id}/extract?device=${encodeURIComponent(byId('device').value)}&language=${encodeURIComponent(byId('language').value)}`, {method:'POST'}); renderProgress(state.job); status('Đã xếp hàng OCR…'); poll(); }
      catch (error) { status(error.message, true); byId('extract').disabled=false; }
    };
    function poll() { clearTimeout(state.poll); state.poll = setTimeout(async () => { try { state.job=await request(`/api/jobs/${state.job.id}`); renderProgress(state.job); const s=state.job.status; if (s==='queued'||s==='running') { const phase=state.job.phase; const message=phase==='initializing' ? 'Đang khởi tạo model OCR…' : phase==='rendering' ? 'Đang render ảnh các trang PDF…' : s==='queued' ? 'Đang chờ tài nguyên OCR…' : 'Đang extract PDF…'; status(message); return poll(); } if (s==='failed') { status(state.job.error || 'Extract thất bại.', true); return; } if (s==='completed') { status(`Hoàn tất: ${state.job.page_count} trang. Chọn box hoặc block để đối chiếu.`); return loadLayout(); } } catch(error) { status(error.message, true); } }, 2500); }
    async function loadLayout() { const data=await request(`/api/jobs/${state.job.id}/layout`); state.pages=data.pages; state.selectedPage=0; state.selectedBlock=null; byId('viewer').hidden=false; render(); }
    function render() { renderPageList(); renderCurrentPage(); renderBlocks(); }
    function renderPageList() { const list=byId('pages'); list.replaceChildren(); state.pages.forEach((page,index) => { const b=document.createElement('button'); b.className='page-button'+(index===state.selectedPage?' active':''); b.textContent=`Trang ${page.page} · ${page.blocks.length} block`; b.onclick=()=>{state.selectedPage=index;state.selectedBlock=null;render();}; list.append(b); }); }
    function renderCurrentPage() { const page=state.pages[state.selectedPage]; const wrap=byId('page-wrap'); wrap.replaceChildren(); const image=document.createElement('img'); image.src=page.image_url; image.alt=`PDF page ${page.page}`; wrap.append(image); page.blocks.forEach((block,index)=>{ if(!block.bbox) return; const [x1,y1,x2,y2]=block.bbox; const box=document.createElement('button'); box.className='box'+(state.selectedBlock===index?' active':''); box.style.left=`${100*x1/page.width}%`; box.style.top=`${100*y1/page.height}%`; box.style.width=`${100*(x2-x1)/page.width}%`; box.style.height=`${100*(y2-y1)/page.height}%`; box.setAttribute('aria-label',`${block.label} block ${index+1}`); const label=document.createElement('span'); label.textContent=`${block.label} #${index+1}`; box.append(label); box.onclick=()=>selectBlock(index); wrap.append(box); }); }
    function selectBlock(index) { state.selectedBlock=index; renderCurrentPage(); renderBlocks(); const card=document.querySelector(`.block[data-index="${index}"]`); if(card) card.scrollIntoView({block:'nearest',behavior:'smooth'}); }
    function shouldShowCrop(label) { return /image|figure|chart|table|formula/i.test(label); }
    function cropPreview(page, block) { if (!block.bbox) return null; const [x1,y1,x2,y2]=block.bbox, bw=x2-x1, bh=y2-y1; if(bw<=0||bh<=0) return null; const crop=document.createElement('div'); crop.className='crop'; crop.style.aspectRatio=`${bw} / ${bh}`; const img=document.createElement('img'); img.src=page.image_url; img.alt=`Cắt từ trang ${page.page}`; img.style.width=`${100*page.width/bw}%`; img.style.left=`-${100*x1/bw}%`; img.style.top=`-${100*y1/bh}%`; crop.append(img); return crop; }
    function renderBlocks() { const page=state.pages[state.selectedPage], list=byId('blocks'); list.replaceChildren(); if(!page.blocks.length) { const empty=document.createElement('p'); empty.className='empty'; empty.textContent='Không có block layout nào cho trang này.'; list.append(empty); return; } page.blocks.forEach((block,index)=>{ const card=document.createElement('article'); card.className='block'+(state.selectedBlock===index?' active':''); card.dataset.index=index; const meta=document.createElement('div'); meta.className='meta'; meta.textContent=`#${block.order} · ${block.label}`; const text=document.createElement('div'); text.className='text'; text.textContent=block.text || '(Không có text; xem vùng cắt từ trang PDF.)'; card.append(meta,text); if(shouldShowCrop(block.label)) { const crop=cropPreview(page,block); if(crop) card.append(crop); } card.onclick=()=>selectBlock(index); list.append(card); }); }
  </script>
</body>
</html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=os.environ.get("PDF_LAYOUT_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PDF_LAYOUT_PORT", "8000")))
    parser.add_argument("--access-log", action="store_true", help="Print every HTTP request (off by default).")
    args = parser.parse_args()
    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, access_log=args.access_log)


if __name__ == "__main__":
    main()
