from uuid import uuid4

from src.models import Order, OrderItem

from tests.conftest import auth_headers


def _create_order(db, status: str = "PAID", buyer_id: str | None = None) -> tuple[Order, str]:
    bid = buyer_id or str(uuid4())
    order = Order(
        buyer_id=bid,
        idempotency_key=uuid4(),
        request_hash="testhash",
        status=status,
        subtotal=1000,
        delivery_cost=0,
        total=1000,
    )
    db.add(order)
    db.flush()
    db.add(OrderItem(
        order_id=order.id,
        sku_id=uuid4(),
        product_id=uuid4(),
        product_title="Test Item",
        sku_name="base",
        quantity=1,
        unit_price=1000,
        line_total=1000,
    ))
    db.commit()
    db.refresh(order)
    return order, bid


def test_cancel_paid_order_transitions_to_cancelled(client, fake_b2b, db):
    order, buyer_id = _create_order(db, status="PAID")

    response = client.post(f"/api/v1/orders/{order.id}/cancel", headers=auth_headers(buyer_id))

    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"
    assert len(fake_b2b.unreserve_calls) == 1


def test_unreserve_failure_transitions_to_cancel_pending(client, fake_b2b, db):
    fake_b2b.unreserve_fails = True
    order, buyer_id = _create_order(db, status="PAID")

    response = client.post(f"/api/v1/orders/{order.id}/cancel", headers=auth_headers(buyer_id))

    assert response.status_code == 200
    assert response.json()["status"] == "CANCEL_PENDING"


def test_cancel_assembling_order_returns_409(client, fake_b2b, db):
    order, buyer_id = _create_order(db, status="ASSEMBLING")

    response = client.post(f"/api/v1/orders/{order.id}/cancel", headers=auth_headers(buyer_id))

    assert response.status_code == 409


def test_other_user_order_returns_404(client, fake_b2b, db):
    order, _buyer_id = _create_order(db, status="PAID")
    other_user = str(uuid4())

    response = client.post(f"/api/v1/orders/{order.id}/cancel", headers=auth_headers(other_user))

    assert response.status_code == 404
