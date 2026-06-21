from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from src.b2b_client import B2BClient, B2BUnavailableError
from src.deps import CartIdentity
from src.models import CartItem


def get_items_for_identity(db: Session, identity: CartIdentity) -> list[CartItem]:
    if identity.user_id is not None:
        stmt = select(CartItem).where(CartItem.user_id == identity.user_id)
    elif identity.session_id:
        stmt = select(CartItem).where(CartItem.session_id == identity.session_id)
    else:
        return []
    return list(db.scalars(stmt).all())


def add_item(
    db: Session,
    identity: CartIdentity,
    sku_id: uuid.UUID,
    product_id: uuid.UUID,
    quantity: int = 1,
) -> CartItem:
    existing: CartItem | None = None
    if identity.user_id is not None:
        existing = db.scalars(
            select(CartItem).where(
                and_(CartItem.user_id == identity.user_id, CartItem.sku_id == sku_id)
            )
        ).first()
    elif identity.session_id:
        existing = db.scalars(
            select(CartItem).where(
                and_(CartItem.session_id == identity.session_id, CartItem.sku_id == sku_id)
            )
        ).first()

    if existing is not None:
        existing.quantity += quantity
        db.commit()
        db.refresh(existing)
        return existing

    item = CartItem(
        user_id=identity.user_id,
        session_id=identity.session_id,
        sku_id=sku_id,
        product_id=product_id,
        quantity=quantity,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def merge_guest_cart(db: Session, user_id: uuid.UUID, session_id: str) -> list[CartItem]:
    guest_items = list(db.scalars(select(CartItem).where(CartItem.session_id == session_id)).all())
    for guest in guest_items:
        auth_item = db.scalars(
            select(CartItem).where(
                and_(CartItem.user_id == user_id, CartItem.sku_id == guest.sku_id)
            )
        ).first()
        if auth_item is not None:
            auth_item.quantity = max(auth_item.quantity, guest.quantity)
            db.delete(guest)
        else:
            guest.user_id = user_id
            guest.session_id = None
    db.commit()
    return list(db.scalars(select(CartItem).where(CartItem.user_id == user_id)).all())


def enrich_cart(items: list[CartItem], b2b: B2BClient) -> list[dict[str, Any]]:
    if not items:
        return []
    product_ids = list({str(item.product_id) for item in items})
    try:
        sku_map = b2b.fetch_skus_by_product(product_ids)
    except B2BUnavailableError:
        sku_map = {}

    result = []
    for item in items:
        sku_data = sku_map.get(str(item.sku_id))
        if sku_data is None:
            result.append({
                "sku_id": str(item.sku_id),
                "product_id": str(item.product_id),
                "quantity": item.quantity,
                "available": False,
                "unavailable_reason": "PRODUCT_NOT_FOUND",
                "product_title": None,
                "sku_name": None,
                "price": None,
                "image_url": None,
            })
        else:
            active_qty = sku_data.get("active_quantity") or 0
            available = int(active_qty) > 0
            result.append({
                "sku_id": str(item.sku_id),
                "product_id": str(item.product_id),
                "quantity": item.quantity,
                "available": available,
                "unavailable_reason": "OUT_OF_STOCK" if not available else None,
                "product_title": sku_data.get("product_title"),
                "sku_name": sku_data.get("name"),
                "price": sku_data.get("price"),
                "image_url": sku_data.get("image_url"),
            })
    return result
