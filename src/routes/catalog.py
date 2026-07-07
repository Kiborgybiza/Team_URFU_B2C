from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

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


def _cover_images(product: dict) -> list[dict]:
    """Build CatalogProductCard.images from the Short response `cover_image`.

    The B2B list response carries a single nullable `cover_image` URL, not an
    images array, so the card shows at most that one image.
    """
    cover = product.get("cover_image")
    if not cover:
        return []
    # ImageRef requires a uuid id, but the Short response only carries a URL, so
    # derive a stable id from it (deterministic, no randomness).
    return [{"id": str(uuid5(NAMESPACE_URL, cover)), "url": cover, "ordering": 0, "is_main": True}]


def _to_catalog_card(product: dict) -> dict:
    """Transform a B2B ProductPublicShortResponse item into CatalogProductCard.

    The B2B public list (`GET /api/v1/public/products`) returns the SHORT form:
    id, title, slug, status, category_id, min_price, cover_image, created_at —
    no `skus`, no `images` array. Values are taken from those fields directly.
    Required per b2c openapi: id, name, min_price, has_stock, images.
    """
    card: dict = {
        "id": product["id"],
        "name": product.get("title") or product.get("name") or "",
        "min_price": product.get("min_price") or 0,
        # The B2B list returns only MODERATED products that have at least one
        # in-stock SKU, so every item present in the list is in stock.
        "has_stock": True,
        "images": _cover_images(product),
    }
    if product.get("slug"):
        card["slug"] = product["slug"]
    return card


@router.get("/api/v1/catalog/products")
def list_products(
    sort: str = Query(default="popularity"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    filter_category_id: str | None = Query(default=None, alias="filter[category_id]"),
    filter_price_min: int | None = Query(default=None, alias="filter[price_min]"),
    filter_price_max: int | None = Query(default=None, alias="filter[price_max]"),
    ids: str | None = Query(default=None),
    b2b: B2BClient = Depends(get_b2b_client),
):
    if sort not in VALID_SORT:
        return JSONResponse(
            status_code=400,
            content={"code": "INVALID_SORT", "message": f"Invalid sort value: {sort}. Valid: {sorted(VALID_SORT)}"},
        )

    # Spec default is popularity; always forward a sort so B2B does not fall
    # back to its own default (created_desc).
    params: dict = {"limit": limit, "offset": offset, "sort": _SORT_TO_B2B[sort]}
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
