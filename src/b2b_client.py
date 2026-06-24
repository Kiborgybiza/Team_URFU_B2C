from __future__ import annotations

from typing import Any

import httpx

from src.config import settings


class B2BError(Exception):
    pass


class B2BUnavailableError(B2BError):
    pass


class B2BNotFoundError(B2BError):
    pass


class B2BReserveConflictError(B2BError):
    pass


class B2BClient:
    def __init__(self, base_url: str | None = None, service_key: str | None = None) -> None:
        self.base_url = (base_url or settings.b2b_url).rstrip("/")
        self.service_key = service_key or settings.b2b_service_key

    def _headers(self) -> dict[str, str]:
        return {"X-Service-Key": self.service_key}

    def fetch_catalog(self, params: dict[str, Any]) -> dict[str, Any]:
        try:
            resp = httpx.get(
                f"{self.base_url}/api/v1/products",
                headers=self._headers(),
                params=params,
                timeout=5.0,
            )
        except httpx.HTTPError as e:
            raise B2BUnavailableError("B2B unavailable") from e
        if resp.status_code >= 500:
            raise B2BUnavailableError("B2B unavailable")
        if not resp.is_success:
            raise B2BUnavailableError(f"B2B error: {resp.status_code}")
        return resp.json()

    def fetch_facets(self, params: dict[str, Any]) -> dict[str, Any]:
        try:
            resp = httpx.get(
                f"{self.base_url}/api/v1/public/facets",
                headers=self._headers(),
                params=params,
                timeout=5.0,
            )
        except httpx.HTTPError as e:
            raise B2BUnavailableError("B2B unavailable") from e
        if resp.status_code >= 500:
            raise B2BUnavailableError("B2B unavailable")
        if not resp.is_success:
            raise B2BUnavailableError(f"B2B error: {resp.status_code}")
        return resp.json()

    def fetch_product(self, product_id: str) -> dict[str, Any]:
        try:
            resp = httpx.get(
                f"{self.base_url}/api/v1/products/{product_id}",
                headers=self._headers(),
                timeout=5.0,
            )
        except httpx.HTTPError as e:
            raise B2BUnavailableError("B2B unavailable") from e
        if resp.status_code == 404:
            raise B2BNotFoundError(f"Product {product_id} not found")
        if not resp.is_success:
            raise B2BUnavailableError("B2B error")
        return resp.json()

    def fetch_skus_by_product(self, product_ids: list[str]) -> dict[str, dict[str, Any]]:
        """Returns mapping of sku_id → sku dict enriched with product info."""
        if not product_ids:
            return {}
        ids_str = ",".join(product_ids)
        try:
            resp = httpx.get(
                f"{self.base_url}/api/v1/products",
                headers=self._headers(),
                params={"ids": ids_str},
                timeout=5.0,
            )
        except httpx.HTTPError as e:
            raise B2BUnavailableError("B2B unavailable") from e
        if not resp.is_success:
            raise B2BUnavailableError("B2B error")
        data = resp.json()
        result: dict[str, dict[str, Any]] = {}
        for product in data.get("items", []):
            images = product.get("images") or []
            image_url = images[0].get("url") if images else None
            for sku in product.get("skus", []):
                result[str(sku["id"])] = {
                    **sku,
                    "product_id": str(product["id"]),
                    "product_title": product.get("title", ""),
                    "image_url": image_url,
                }
        return result

    def reserve(self, idempotency_key: str, items: list[dict[str, Any]], order_id: str | None = None) -> None:
        try:
            resp = httpx.post(
                f"{self.base_url}/api/v1/inventory/reserve",
                json={"idempotency_key": idempotency_key, "order_id": order_id or idempotency_key, "items": items},
                headers=self._headers(),
                timeout=5.0,
            )
        except httpx.HTTPError as e:
            raise B2BUnavailableError("B2B unavailable") from e
        if resp.status_code == 409:
            raise B2BReserveConflictError("Partial reserve failure")
        if not resp.is_success:
            raise B2BUnavailableError("B2B reserve failed")

    def unreserve(self, order_id: str, items: list[dict[str, Any]]) -> None:
        try:
            resp = httpx.post(
                f"{self.base_url}/api/v1/inventory/unreserve",
                json={"order_id": order_id, "items": items},
                headers=self._headers(),
                timeout=5.0,
            )
        except httpx.HTTPError as e:
            raise B2BUnavailableError("B2B unavailable") from e
        if not resp.is_success:
            raise B2BUnavailableError("B2B unreserve failed")


def get_b2b_client() -> B2BClient:
    return B2BClient()
