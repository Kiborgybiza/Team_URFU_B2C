from uuid import uuid4

from tests.conftest import auth_headers


def _setup_cart(client, fake_b2b, user_id: str, price: int = 1000, qty: int = 1) -> tuple[str, str]:
    product_id = str(uuid4())
    sku_id = str(uuid4())
    fake_b2b.add_product({
        "id": product_id,
        "title": "Checkout Product",
        "skus": [{"id": sku_id, "name": "base", "price": price, "active_quantity": 20}],
    })
    client.post(
        "/api/v1/cart/items",
        json={"sku_id": sku_id, "product_id": product_id, "quantity": qty},
        headers=auth_headers(user_id),
    )
    return product_id, sku_id


def _checkout_headers(user_id: str, idempotency_key: str | None = None) -> dict:
    return {**auth_headers(user_id), "Idempotency-Key": idempotency_key or str(uuid4())}


def _checkout_body(**overrides) -> dict:
    payload: dict = {
        "address_id": str(uuid4()),
        "payment_method_id": str(uuid4()),
    }
    payload.update(overrides)
    return payload


def test_checkout_creates_paid_order_with_fixed_prices(client, fake_b2b):
    user_id = str(uuid4())
    _setup_cart(client, fake_b2b, user_id, price=1500, qty=2)

    response = client.post(
        "/api/v1/orders",
        json=_checkout_body(),
        headers=_checkout_headers(user_id),
    )

    assert response.status_code == 201
    order = response.json()
    assert order["status"] == "PAID"
    assert order["total"] == 3000
    assert len(order["items"]) == 1
    assert order["items"][0]["unit_price"] == 1500
    assert order["items"][0]["line_total"] == 3000
    assert len(fake_b2b.reserve_calls) == 1


def test_partial_reserve_failure_returns_409(client, fake_b2b):
    user_id = str(uuid4())
    _setup_cart(client, fake_b2b, user_id)
    fake_b2b.reserve_conflict = True

    response = client.post(
        "/api/v1/orders",
        json=_checkout_body(),
        headers=_checkout_headers(user_id),
    )

    assert response.status_code == 409


def test_idempotency_returns_existing_order(client, fake_b2b):
    user_id = str(uuid4())
    _setup_cart(client, fake_b2b, user_id, price=500)
    idem_key = str(uuid4())

    resp1 = client.post(
        "/api/v1/orders",
        json=_checkout_body(),
        headers=_checkout_headers(user_id, idempotency_key=idem_key),
    )
    assert resp1.status_code == 201
    order_id = resp1.json()["id"]

    resp2 = client.post(
        "/api/v1/orders",
        json=_checkout_body(),
        headers=_checkout_headers(user_id, idempotency_key=idem_key),
    )
    assert resp2.status_code == 201
    assert resp2.json()["id"] == order_id


def test_b2b_unavailable_returns_503(client, fake_b2b):
    user_id = str(uuid4())
    _setup_cart(client, fake_b2b, user_id)
    fake_b2b.b2b_unavailable = True

    response = client.post(
        "/api/v1/orders",
        json=_checkout_body(),
        headers=_checkout_headers(user_id),
    )

    assert response.status_code == 503
    assert response.json()["code"] == "B2B_UNAVAILABLE"
