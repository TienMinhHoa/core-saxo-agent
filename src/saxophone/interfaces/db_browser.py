"""Read-only web console for inspecting configured Chroma collections."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse


def build_database_browser_router(
    *,
    browser: Any = None,
    assets_root: Path | None = None,
) -> APIRouter:
    root = assets_root or Path(__file__).with_name("api") / "assets" / "db"
    if not isinstance(root, Path):
        raise TypeError("assets_root must be a Path")
    router = APIRouter()
    assets = {
        "db.css": (root / "db.css", "text/css"),
        "db.js": (root / "db.js", "application/javascript"),
    }

    @router.get("/db", include_in_schema=False)
    async def database_page() -> FileResponse:
        return FileResponse(root / "index.html", media_type="text/html")

    @router.get("/db/assets/{asset_name}", include_in_schema=False)
    async def database_asset(asset_name: str) -> FileResponse:
        asset = assets.get(asset_name)
        if asset is None:
            raise HTTPException(status_code=404, detail="database browser asset not found")
        path, media_type = asset
        return FileResponse(path, media_type=media_type)

    @router.get("/db/api/collections", include_in_schema=False)
    async def collections() -> dict[str, object]:
        active_browser = _required_browser(browser)
        summaries = await active_browser.list_collections()
        return {
            "collections": [
                {"name": summary.name, "count": summary.count}
                for summary in summaries
            ]
        }

    @router.get(
        "/db/api/collections/{collection_name}/records",
        include_in_schema=False,
    )
    async def records(
        collection_name: str,
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=25, ge=1, le=100),
        q: str | None = Query(default=None, max_length=500),
        document_ref: str | None = Query(default=None, max_length=500),
    ) -> dict[str, object]:
        active_browser = _required_browser(browser)
        try:
            page = await active_browser.get_records(
                collection_name,
                offset=offset,
                limit=limit,
                query=_optional_text(q),
                document_ref=_optional_text(document_ref),
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return {
            "collection": page.collection_name,
            "offset": page.offset,
            "limit": page.limit,
            "total_count": page.total_count,
            "has_more": page.has_more,
            "records": [
                {
                    "id": record.record_id,
                    "document": record.document,
                    "metadata": dict(record.metadata),
                }
                for record in page.records
            ],
        }

    return router


def _required_browser(browser: Any) -> Any:
    if browser is None:
        raise HTTPException(
            status_code=503,
            detail="Chroma database browser is not configured",
        )
    return browser


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None
