from uuid import uuid4

from tests.conftest import auth_headers


def _make_product(price: int = 1000, active_quantity: int = 5) -> tuple[dict, str, str]:
    product_id = str(uuid4())
    sku_id = str(uuid4())
    product = {
        "id": product_id,
        "title": "Test Product",
        "status": "MODERATED",
        "skus": [{"id": sku_id, "name": "base", "price": price, "active_quantity": active_quantity}],
    }
    return product, product_id, sku_id


def test_add_sku_increments_quantity_if_already_in_cart(client, fake_b2b):
    product, product_id, sku_id = _make_product()
    fake_b2b.add_product(product)
    user_id = str(uuid4())
    headers = auth_headers(user_id)

    client.post(
        "/api/v1/cart/items",
        json={"sku_id": sku_id, "product_id": product_id, "quantity": 1},
        headers=headers,
    )
    client.post(
        "/api/v1/cart/items",
        json={"sku_id": sku_id, "product_id": product_id, "quantity": 2},
        headers=headers,
    )

    response = client.get("/api/v1/cart", headers=headers)
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["quantity"] == 3


def test_get_cart_enriched_with_b2b_data(client, fake_b2b):
    product, product_id, sku_id = _make_product(price=2500)
    fake_b2b.add_product(product)
    user_id = str(uuid4())
    headers = auth_headers(user_id)

    client.post(
        "/api/v1/cart/items",
        json={"sku_id": sku_id, "product_id": product_id, "quantity": 1},
        headers=headers,
    )

    response = client.get("/api/v1/cart", headers=headers)
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    item = items[0]
    assert item["product_title"] == "Test Product"
    assert item["price"] == 2500
    assert item["available"] is True
    assert item["sku_id"] == sku_id


def test_unavailable_sku_shown_with_reason(client, fake_b2b):
    product_id = str(uuid4())
    sku_id = str(uuid4())
    fake_b2b.add_product({
        "id": product_id,
        "title": "OOS Product",
        "skus": [{"id": sku_id, "name": "base", "price": 999, "active_quantity": 0}],
    })
    user_id = str(uuid4())
    headers = auth_headers(user_id)

    client.post(
        "/api/v1/cart/items",
        json={"sku_id": sku_id, "product_id": product_id, "quantity": 1},
        headers=headers,
    )

    response = client.get("/api/v1/cart", headers=headers)
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    item = items[0]
    assert item["available"] is False
    assert item["unavailable_reason"] is not None
    assert "OUT_OF_STOCK" in item["unavailable_reason"]


def test_guest_cart_merged_on_login(client, fake_b2b):
    product_id = str(uuid4())
    sku_id = str(uuid4())
    sku_id2 = str(uuid4())
    fake_b2b.add_product({
        "id": product_id,
        "title": "Merge Product",
        "skus": [
            {"id": sku_id, "name": "red", "price": 1000, "active_quantity": 10},
            {"id": sku_id2, "name": "blue", "price": 2000, "active_quantity": 5},
        ],
    })
    session_id = str(uuid4())
    user_id = str(uuid4())

    # Guest: sku_id qty=2, sku_id2 qty=1
    client.post(
        "/api/v1/cart/items",
        json={"sku_id": sku_id, "product_id": product_id, "quantity": 2},
        headers={"X-Session-Id": session_id},
    )
    client.post(
        "/api/v1/cart/items",
        json={"sku_id": sku_id2, "product_id": product_id, "quantity": 1},
        headers={"X-Session-Id": session_id},
    )

    # Auth user already has sku_id qty=1
    client.post(
        "/api/v1/cart/items",
        json={"sku_id": sku_id, "product_id": product_id, "quantity": 1},
        headers=auth_headers(user_id),
    )

    # Merge → sku_id gets max(2,1)=2; sku_id2 gets 1
    response = client.post(
        "/api/v1/cart/merge",
        headers={**auth_headers(user_id), "X-Session-Id": session_id},
    )
    assert response.status_code == 200
    items = response.json()["items"]
    by_sku = {item["sku_id"]: item for item in items}
    assert by_sku[sku_id]["quantity"] == 2
    assert by_sku[sku_id2]["quantity"] == 1
