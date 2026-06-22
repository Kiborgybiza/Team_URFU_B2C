from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.b2b_client import B2BClient, get_b2b_client
from src.database import get_db
from src.deps import CartIdentity, get_cart_identity, get_jwt_user_id
from src.services.cart_service import (
    add_item,
    enrich_cart,
    get_items_for_identity,
    merge_guest_cart,
)

router = APIRouter(tags=["Cart"])


class AddItemRequest(BaseModel):
    sku_id: uuid.UUID
    product_id: uuid.UUID | None = None
    quantity: int = 1


def _cart_response(enriched: list[dict[str, Any]]) -> dict[str, Any]:
    items_count = sum(item["quantity"] for item in enriched)
    subtotal = sum(
        item["unit_price"] * item["quantity"]
        for item in enriched
        if item["is_available"] and item["unit_price"] is not None
    )
    is_valid = all(item["is_available"] for item in enriched) if enriched else True
    return {"items": enriched, "items_count": items_count, "subtotal": subtotal, "is_valid": is_valid}


@router.get("/api/v1/cart")
def get_cart(
    identity: CartIdentity = Depends(get_cart_identity),
    db: Session = Depends(get_db),
    b2b: B2BClient = Depends(get_b2b_client),
):
    items = get_items_for_identity(db, identity)
    return _cart_response(enrich_cart(items, b2b))


@router.post("/api/v1/cart/items", status_code=201)
def add_cart_item(
    request: AddItemRequest,
    identity: CartIdentity = Depends(get_cart_identity),
    db: Session = Depends(get_db),
    b2b: B2BClient = Depends(get_b2b_client),
):
    if identity.user_id is None and not identity.session_id:
        return JSONResponse(
            status_code=401,
            content={"code": "UNAUTHORIZED", "message": "Auth or X-Session-Id required"},
        )
    add_item(db, identity, request.sku_id, request.product_id, request.quantity)
    items = get_items_for_identity(db, identity)
    return _cart_response(enrich_cart(items, b2b))


@router.post("/api/v1/cart/merge")
def merge_cart(
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
    user_id: uuid.UUID | JSONResponse = Depends(get_jwt_user_id),
    db: Session = Depends(get_db),
    b2b: B2BClient = Depends(get_b2b_client),
):
    if isinstance(user_id, JSONResponse):
        return user_id
    if not x_session_id:
        return JSONResponse(
            status_code=400,
            content={"code": "SESSION_REQUIRED", "message": "X-Session-Id header is required"},
        )
    items = merge_guest_cart(db, user_id, x_session_id)
    return _cart_response(enrich_cart(items, b2b))
