from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.b2b_client import B2BClient, B2BReserveConflictError, B2BUnavailableError
from src.models import CartItem, Order, OrderItem


class OrderConflictError(Exception):
    pass


class OrderNotFoundError(Exception):
    pass


class OrderCancelError(Exception):
    pass


def _hash_cart(items: list[dict[str, Any]]) -> str:
    normalized = sorted(items, key=lambda i: i["sku_id"])
    return hashlib.sha256(json.dumps(normalized, sort_keys=True).encode()).hexdigest()


CANCELLABLE_STATUSES = {"PAID"}


def checkout(
    db: Session,
    buyer_id: uuid.UUID,
    idempotency_key: uuid.UUID,
    address_id: uuid.UUID | None,
    payment_method_id: uuid.UUID | None,
    b2b: B2BClient,
) -> Order:
    # Idempotency check first — before any expensive work
    existing = db.scalars(select(Order).where(Order.idempotency_key == idempotency_key)).first()
    if existing is not None:
        return existing

    cart_items = list(db.scalars(select(CartItem).where(CartItem.user_id == buyer_id)).all())
    if not cart_items:
        raise OrderConflictError("Cart is empty")

    product_ids = list({str(item.product_id) for item in cart_items})
    try:
        sku_map = b2b.fetch_skus_by_product(product_ids)
    except B2BUnavailableError:
        raise

    order_items_data: list[dict[str, Any]] = []
    for ci in cart_items:
        sku = sku_map.get(str(ci.sku_id))
        if sku is None:
            raise OrderConflictError(f"SKU {ci.sku_id} is not available")
        order_items_data.append({
            "sku_id": str(ci.sku_id),
            "product_id": str(ci.product_id),
            "product_title": sku.get("product_title", ""),
            "sku_name": sku.get("name", ""),
            "quantity": ci.quantity,
            "unit_price": int(sku["price"]),
            "line_total": int(sku["price"]) * ci.quantity,
            "image_url": sku.get("image_url"),
        })

    request_hash = _hash_cart([{"sku_id": d["sku_id"], "quantity": d["quantity"]} for d in order_items_data])
    subtotal = sum(d["line_total"] for d in order_items_data)

    reserve_items = [{"sku_id": d["sku_id"], "quantity": d["quantity"]} for d in order_items_data]
    try:
        b2b.reserve(str(idempotency_key), reserve_items)
    except B2BReserveConflictError as e:
        raise OrderConflictError("Partial reserve failure") from e
    except B2BUnavailableError:
        raise

    order = Order(
        buyer_id=buyer_id,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        status="PAID",
        subtotal=subtotal,
        delivery_cost=0,
        total=subtotal,
        address_id=address_id,
        payment_method_id=payment_method_id,
    )
    db.add(order)
    db.flush()

    for d in order_items_data:
        db.add(OrderItem(order_id=order.id, **d))

    db.commit()
    db.refresh(order)
    return order


def cancel_order(
    db: Session,
    order_id: uuid.UUID,
    buyer_id: uuid.UUID,
    b2b: B2BClient,
) -> Order:
    order = db.scalars(
        select(Order).where(Order.id == order_id, Order.buyer_id == buyer_id)
    ).first()
    if order is None:
        raise OrderNotFoundError(f"Order {order_id} not found")
    if order.status not in CANCELLABLE_STATUSES:
        raise OrderCancelError(f"Cannot cancel order in status {order.status}")

    unreserve_items = [
        {"sku_id": str(item.sku_id), "quantity": item.quantity}
        for item in order.items
    ]
    try:
        b2b.unreserve(str(order_id), unreserve_items)
        order.status = "CANCELLED"
    except B2BUnavailableError:
        order.status = "CANCEL_PENDING"

    db.commit()
    db.refresh(order)
    return order
