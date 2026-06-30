from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from src.b2b_client import B2BClient, B2BNotFoundError, B2BUnavailableError, get_b2b_client

router = APIRouter(tags=["Catalog"])

VALID_SORT = {"price_asc", "price_desc", "popularity", "new"}

_SORT_TO_B2B = {"price_asc": "price_asc", "price_desc": "price_desc", "popularity": "popular", "new": "created_desc"}


def _strip_private(product: dict) -> dict:
    result = {k: v for k, v in product.items() if k != "cost_price"}
    if "skus" in result:
        result["skus"] = [
            {k: v for k, v in sku.items() if k not in ("cost_price", "reserved_quantity")}
            for sku in result["skus"]
        ]
    return result


def _image_ref(img: dict) -> dict:
    """Map a B2B image into the openapi ImageRef shape (id, url, ordering)."""
    ref = {
        "id": img.get("id"),
        "url": img.get("url", ""),
        "ordering": img.get("ordering", 0),
    }
    if img.get("alt") is not None:
        ref["alt"] = img["alt"]
    if img.get("is_main") is not None:
        ref["is_main"] = img["is_main"]
    return ref


def _to_catalog_card(product: dict) -> dict:
    """Transform a raw B2B product into the b2c openapi CatalogProductCard schema.

    Required fields per spec: id, name, min_price, has_stock, images.
    """
    skus = [s for s in product.get("skus", []) if not s.get("deleted", False)]
    in_stock_skus = [s for s in skus if s.get("active_quantity", 0) > 0]
    priced = [s["price"] for s in (in_stock_skus or skus) if s.get("price") is not None]

    card: dict = {
        "id": product["id"],
        "name": product.get("title") or product.get("name") or "",
        "min_price": min(priced) if priced else 0,
        "has_stock": bool(in_stock_skus),
        "images": [_image_ref(i) for i in (product.get("images") or [])],
    }
    if product.get("slug"):
        card["slug"] = product["slug"]
    if product.get("category"):
        card["category"] = product["category"]
    if product.get("seller_id"):
        card["seller"] = {"id": str(product["seller_id"])}
    return card


@router.get("/api/v1/catalog/products")
def list_products(
    sort: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    filter_category_id: str | None = Query(default=None, alias="filter[category_id]"),
    filter_price_min: int | None = Query(default=None, alias="filter[price_min]"),
    filter_price_max: int | None = Query(default=None, alias="filter[price_max]"),
    ids: str | None = Query(default=None),
    b2b: B2BClient = Depends(get_b2b_client),
):
    if sort is not None and sort not in VALID_SORT:
        return JSONResponse(
            status_code=400,
            content={"code": "INVALID_SORT", "message": f"Invalid sort value: {sort}. Valid: {sorted(VALID_SORT)}"},
        )

    params: dict = {"limit": limit, "offset": offset}
    if sort:
        params["sort"] = _SORT_TO_B2B[sort]
    if filter_category_id:
        params["category_id"] = filter_category_id
    if filter_price_min is not None:
        params["min_price"] = filter_price_min
    if filter_price_max is not None:
        params["max_price"] = filter_price_max
    if ids:
        params["ids"] = ids

    try:
        raw = b2b.fetch_catalog(params)
    except B2BUnavailableError:
        return JSONResponse(
            status_code=502,
            content={"code": "B2B_UNAVAILABLE", "message": "Catalog service unavailable"},
        )

    items = [_to_catalog_card(p) for p in raw.get("items", [])]
    return {
        "items": items,
        "total_count": raw.get("total_count", len(items)),
        "limit": limit,
        "offset": offset,
    }


@router.get("/api/v1/catalog/products/{product_id}")
def get_product(
    product_id: str,
    b2b: B2BClient = Depends(get_b2b_client),
):
    try:
        product = b2b.fetch_product(product_id)
    except B2BNotFoundError:
        return JSONResponse(status_code=404, content={"code": "NOT_FOUND", "message": "Product not found"})
    except B2BUnavailableError:
        return JSONResponse(status_code=502, content={"code": "B2B_UNAVAILABLE", "message": "B2B unavailable"})
    return _strip_private(product)


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
