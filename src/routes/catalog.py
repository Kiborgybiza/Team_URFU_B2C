from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from src.b2b_client import B2BClient, B2BUnavailableError, get_b2b_client

router = APIRouter(tags=["Catalog"])

VALID_SORT = {"price_asc", "price_desc", "created_at_asc", "created_at_desc", "popularity_desc"}


@router.get("/api/v1/products")
def list_products(
    sort: str | None = Query(default=None),
    category_id: str | None = Query(default=None),
    min_price: int | None = Query(default=None),
    max_price: int | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    ids: str | None = Query(default=None),
    b2b: B2BClient = Depends(get_b2b_client),
):
    if sort is not None and sort not in VALID_SORT:
        return JSONResponse(
            status_code=400,
            content={"code": "INVALID_SORT", "message": f"Invalid sort value: {sort}. Valid: {sorted(VALID_SORT)}"},
        )

    params: dict = {"page": page, "per_page": per_page}
    if sort:
        params["sort"] = sort
    if category_id:
        params["category_id"] = category_id
    if min_price is not None:
        params["min_price"] = min_price
    if max_price is not None:
        params["max_price"] = max_price
    if ids:
        params["ids"] = ids

    try:
        return b2b.fetch_catalog(params)
    except B2BUnavailableError:
        return JSONResponse(
            status_code=502,
            content={"code": "B2B_UNAVAILABLE", "message": "Catalog service unavailable"},
        )


@router.get("/api/v1/catalog/facets")
def get_facets(
    category_id: str | None = Query(default=None),
    b2b: B2BClient = Depends(get_b2b_client),
):
    params: dict = {}
    if category_id:
        params["category_id"] = category_id
    try:
        return b2b.fetch_facets(params)
    except B2BUnavailableError:
        return JSONResponse(
            status_code=502,
            content={"code": "B2B_UNAVAILABLE", "message": "Catalog service unavailable"},
        )
