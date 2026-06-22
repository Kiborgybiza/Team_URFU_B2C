from uuid import uuid4


def test_product_card_returns_full_data_with_skus(client, fake_b2b):
    product_id = str(uuid4())
    sku_id = str(uuid4())
    fake_b2b.add_product({
        "id": product_id,
        "title": "Smartphone Pro",
        "description": "A great phone",
        "status": "MODERATED",
        "category": {"id": str(uuid4()), "name": "Electronics"},
        "images": [{"url": "/s3/phone.jpg", "ordering": 0}],
        "skus": [
            {"id": sku_id, "name": "black 128GB", "price": 50000, "active_quantity": 10}
        ],
    })

    response = client.get(f"/api/v1/catalog/products/{product_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == product_id
    assert data["title"] == "Smartphone Pro"
    assert len(data["skus"]) == 1
    assert data["skus"][0]["id"] == sku_id
    assert data["skus"][0]["price"] == 50000


def test_cost_price_absent_in_response(client, fake_b2b):
    product_id = str(uuid4())
    fake_b2b.add_product({
        "id": product_id,
        "title": "Laptop",
        "status": "MODERATED",
        "skus": [
            {
                "id": str(uuid4()),
                "name": "base",
                "price": 100000,
                "cost_price": 70000,
                "reserved_quantity": 5,
                "active_quantity": 3,
            }
        ],
    })

    response = client.get(f"/api/v1/catalog/products/{product_id}")

    assert response.status_code == 200
    body = response.json()
    for sku in body["skus"]:
        assert "cost_price" not in sku
        assert "reserved_quantity" not in sku


def test_blocked_product_returns_404(client, fake_b2b):
    product_id = str(uuid4())
    fake_b2b.block_product(product_id)

    response = client.get(f"/api/v1/catalog/products/{product_id}")

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"
