from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.b2b_client import B2BClient, B2BUnavailableError, get_b2b_client
from src.database import get_db
from src.deps import get_jwt_user_id
from src.models import Order
from src.services.order_service import (
    OrderConflictError,
    checkout,
)

router = APIRouter(tags=["Orders"])


class CheckoutRequest(BaseModel):
    idempotency_key: uuid.UUID
    address_id: uuid.UUID | None = None
    payment_method_id: uuid.UUID | None = None


def _order_out(order: Order) -> dict[str, Any]:
    return {
        "id": str(order.id),
        "buyer_id": str(order.buyer_id),
        "status": order.status,
        "subtotal": order.subtotal,
        "delivery_cost": order.delivery_cost,
        "total": order.total,
        "idempotency_key": str(order.idempotency_key),
        "address_id": str(order.address_id) if order.address_id else None,
        "payment_method_id": str(order.payment_method_id) if order.payment_method_id else None,
        "created_at": order.created_at.isoformat(),
        "items": [
            {
                "id": str(item.id),
                "sku_id": str(item.sku_id),
                "product_id": str(item.product_id),
                "product_title": item.product_title,
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
    user_id: uuid.UUID | JSONResponse = Depends(get_jwt_user_id),
    db: Session = Depends(get_db),
    b2b: B2BClient = Depends(get_b2b_client),
):
    if isinstance(user_id, JSONResponse):
        return user_id
    try:
        order = checkout(
            db,
            buyer_id=user_id,
            idempotency_key=request.idempotency_key,
            address_id=request.address_id,
            payment_method_id=request.payment_method_id,
            b2b=b2b,
        )
    except OrderConflictError as e:
        return JSONResponse(status_code=409, content={"code": "ORDER_CONFLICT", "message": str(e)})
    except B2BUnavailableError:
        return JSONResponse(status_code=503, content={"code": "B2B_UNAVAILABLE", "message": "B2B service unavailable"})
    return JSONResponse(status_code=201, content=_order_out(order))
