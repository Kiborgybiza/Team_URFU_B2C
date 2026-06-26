from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.b2b_client import B2BClient, B2BUnavailableError, get_b2b_client
from src.database import get_db
from src.deps import get_jwt_user_id
from src.models import Order
from src.services.order_service import (
    OrderCancelError,
    OrderConflictError,
    OrderNotFoundError,
    cancel_order,
    checkout,
)

router = APIRouter(tags=["Orders"])


class CheckoutRequest(BaseModel):
    address_id: uuid.UUID
    payment_method_id: uuid.UUID
    address_country: str = ""
    address_city: str = ""
    address_street: str = ""
    address_building: str = ""


def _order_out(order: Order) -> dict[str, Any]:
    return {
        "id": str(order.id),
        "buyer_id": str(order.buyer_id),
        "status": order.status,
        "subtotal": order.subtotal,
        "delivery_cost": order.delivery_cost,
        "total": order.total,
        "idempotency_key": str(order.idempotency_key),
        "address": {
            "id": str(order.address_id),
            "country": order.address_country or "",
            "city": order.address_city or "",
            "street": order.address_street or "",
            "building": order.address_building or "",
            "created_at": order.created_at.isoformat(),
        },
        "payment_method_id": str(order.payment_method_id) if order.payment_method_id else None,
        "created_at": order.created_at.isoformat(),
        "items": [
            {
                "id": str(item.id),
                "sku_id": str(item.sku_id),
                "product_id": str(item.product_id),
                "name": item.product_title,
                "sku_name": item.sku_name,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "line_total": item.line_total,
                "image_url": item.image_url,
            }
            for item in order.items
        ],
    }


@router.post("/api/v1/orders", status_code=201)
def create_order(
    request: CheckoutRequest,
    idempotency_key_header: str | None = Header(default=None, alias="Idempotency-Key"),
    user_id: uuid.UUID | JSONResponse = Depends(get_jwt_user_id),
    db: Session = Depends(get_db),
    b2b: B2BClient = Depends(get_b2b_client),
):
    if isinstance(user_id, JSONResponse):
        return user_id
    if idempotency_key_header is None:
        return JSONResponse(
            status_code=400,
            content={"code": "MISSING_IDEMPOTENCY_KEY", "message": "Idempotency-Key header is required"},
        )
    try:
        idempotency_key = uuid.UUID(idempotency_key_header)
    except ValueError:
        return JSONResponse(
            status_code=400,
            content={"code": "INVALID_IDEMPOTENCY_KEY", "message": "Idempotency-Key must be a valid UUID"},
        )
    try:
        order = checkout(
            db,
            buyer_id=user_id,
            idempotency_key=idempotency_key,
            address_id=request.address_id,
            payment_method_id=request.payment_method_id,
            address_country=request.address_country,
            address_city=request.address_city,
            address_street=request.address_street,
            address_building=request.address_building,
            b2b=b2b,
        )
    except OrderConflictError as e:
        return JSONResponse(status_code=409, content={"code": "RESERVE_FAILED", "message": str(e), "failed_items": e.failed_items})
    except B2BUnavailableError:
        return JSONResponse(status_code=503, content={"code": "B2B_UNAVAILABLE", "message": "B2B service unavailable"})
    return JSONResponse(status_code=201, content=_order_out(order))


@router.post("/api/v1/orders/{order_id}/cancel")
def cancel(
    order_id: uuid.UUID,
    user_id: uuid.UUID | JSONResponse = Depends(get_jwt_user_id),
    db: Session = Depends(get_db),
    b2b: B2BClient = Depends(get_b2b_client),
):
    if isinstance(user_id, JSONResponse):
        return user_id
    try:
        order = cancel_order(db, order_id, user_id, b2b)
    except OrderNotFoundError:
        return JSONResponse(status_code=404, content={"code": "NOT_FOUND", "message": "Order not found"})
    except OrderCancelError as e:
        return JSONResponse(status_code=409, content={"code": "CANCEL_NOT_ALLOWED", "message": str(e)})
    return _order_out(order)
