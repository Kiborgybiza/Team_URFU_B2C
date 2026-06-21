from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from src.database import Base


class GUID(TypeDecorator):
    impl = String(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return str(value) if value is not None else None

    def process_result_value(self, value, dialect):
        return uuid.UUID(str(value)) if value is not None else None


def _now() -> datetime:
    return datetime.now(timezone.utc)


class CartItem(Base):
    __tablename__ = "cart_items"
    __table_args__ = (
        UniqueConstraint("user_id", "sku_id", name="uq_user_sku"),
        UniqueConstraint("session_id", "sku_id", name="uq_session_sku"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(GUID, nullable=True, index=True)
    session_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    sku_id: Mapped[uuid.UUID] = mapped_column(GUID, nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(GUID, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(default=_now)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    buyer_id: Mapped[uuid.UUID] = mapped_column(GUID, nullable=False, index=True)
    idempotency_key: Mapped[uuid.UUID] = mapped_column(GUID, unique=True, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), default="PAID")
    subtotal: Mapped[int] = mapped_column(Integer, default=0)
    delivery_cost: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    address_id: Mapped[uuid.UUID | None] = mapped_column(GUID, nullable=True)
    payment_method_id: Mapped[uuid.UUID | None] = mapped_column(GUID, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_now)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now)

    items: Mapped[list[OrderItem]] = relationship("OrderItem", back_populates="order", lazy="selectin")


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("orders.id"), nullable=False)
    sku_id: Mapped[uuid.UUID] = mapped_column(GUID, nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(GUID, nullable=False)
    product_title: Mapped[str] = mapped_column(String(512), nullable=False)
    sku_name: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[int] = mapped_column(Integer, nullable=False)
    line_total: Mapped[int] = mapped_column(Integer, nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_now)

    order: Mapped[Order] = relationship("Order", back_populates="items")
