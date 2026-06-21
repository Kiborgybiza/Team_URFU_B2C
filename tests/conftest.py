from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.b2b_client import (
    B2BClient,
    B2BNotFoundError,
    B2BReserveConflictError,
    B2BUnavailableError,
    get_b2b_client,
)
from src.database import Base, get_db
from src.main import app


def make_jwt(user_id: str, secret: str = "secret") -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').rstrip(b"=").decode()
    payload_bytes = json.dumps({"sub": user_id}).encode()
    payload = base64.urlsafe_b64encode(payload_bytes).rstrip(b"=").decode()
    sig_input = f"{header}.{payload}".encode("ascii")
    signature = hmac.new(secret.encode(), sig_input, hashlib.sha256).digest()
    sig = base64.urlsafe_b64encode(signature).rstrip(b"=").decode()
    return f"{header}.{payload}.{sig}"


def auth_headers(user_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_jwt(user_id)}"}


class FakeB2BClient(B2BClient):
    def __init__(self) -> None:
        self._products: dict[str, dict[str, Any]] = {}
        self._catalog_response: dict[str, Any] = {"items": []}
        self._facets_response: dict[str, Any] = {"facets": []}
        self._blocked_ids: set[str] = set()
        self.catalog_unavailable: bool = False
        self.b2b_unavailable: bool = False
        self.reserve_conflict: bool = False
        self.unreserve_fails: bool = False
        self.reserve_calls: list[dict[str, Any]] = []
        self.unreserve_calls: list[dict[str, Any]] = []

    def add_product(self, product: dict[str, Any]) -> None:
        self._products[str(product["id"])] = product

    def block_product(self, product_id: str) -> None:
        self._blocked_ids.add(product_id)

    def set_catalog_response(self, items: list[dict[str, Any]]) -> None:
        self._catalog_response = {"items": items}

    def set_facets_response(self, response: dict[str, Any]) -> None:
        self._facets_response = response

    def fetch_catalog(self, params: dict[str, Any]) -> dict[str, Any]:
        if self.catalog_unavailable or self.b2b_unavailable:
            raise B2BUnavailableError("B2B unavailable")
        return self._catalog_response

    def fetch_facets(self, params: dict[str, Any]) -> dict[str, Any]:
        if self.b2b_unavailable:
            raise B2BUnavailableError("B2B unavailable")
        return self._facets_response

    def fetch_product(self, product_id: str) -> dict[str, Any]:
        if self.b2b_unavailable:
            raise B2BUnavailableError("B2B unavailable")
        if product_id in self._blocked_ids or product_id not in self._products:
            raise B2BNotFoundError(f"Product {product_id} not found")
        return self._products[product_id]

    def fetch_skus_by_product(self, product_ids: list[str]) -> dict[str, dict[str, Any]]:
        if self.b2b_unavailable:
            raise B2BUnavailableError("B2B unavailable")
        result: dict[str, dict[str, Any]] = {}
        for pid in product_ids:
            product = self._products.get(pid)
            if product is None:
                continue
            images = product.get("images") or []
            image_url = images[0].get("url") if images else None
            for sku in product.get("skus", []):
                result[str(sku["id"])] = {
                    **sku,
                    "product_id": pid,
                    "product_title": product.get("title", ""),
                    "image_url": image_url,
                }
        return result

    def reserve(self, idempotency_key: str, items: list[dict[str, Any]]) -> None:
        self.reserve_calls.append({"idempotency_key": idempotency_key, "items": items})
        if self.b2b_unavailable:
            raise B2BUnavailableError("B2B unavailable")
        if self.reserve_conflict:
            raise B2BReserveConflictError("Partial reserve failure")

    def unreserve(self, order_id: str, items: list[dict[str, Any]]) -> None:
        self.unreserve_calls.append({"order_id": order_id, "items": items})
        if self.unreserve_fails:
            raise B2BUnavailableError("B2B unreserve failed")


@pytest.fixture
def fake_b2b() -> FakeB2BClient:
    return FakeB2BClient()


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def client(db, fake_b2b):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_b2b_client] = lambda: fake_b2b
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
