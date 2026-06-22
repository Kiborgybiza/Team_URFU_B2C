from uuid import uuid4


def _product(price: int = 1000, category_id: str | None = None) -> dict:
    pid = str(uuid4())
    return {
        "id": pid,
        "title": "Test Product",
        "description": "Description",
        "status": "MODERATED",
        "category": {"id": category_id or str(uuid4()), "name": "Electronics"},
        "images": [{"url": "/s3/img.jpg", "ordering": 0}],
        "skus": [{"id": str(uuid4()), "name": "base", "price": price, "active_quantity": 5}],
    }


def test_catalog_returns_filtered_sorted_products(client, fake_b2b):
    p1 = _product(price=500)
    p2 = _product(price=1500)
    fake_b2b.set_catalog_response([p1, p2])

    response = client.get("/api/v1/catalog/products", params={"sort": "price_asc"})

    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert len(data["items"]) == 2
    assert data["items"][0]["id"] == p1["id"]
    assert data["items"][1]["id"] == p2["id"]


def test_facets_return_counts_per_filter_value(client, fake_b2b):
    cat_id = str(uuid4())
    fake_b2b.set_facets_response({
        "facets": [
            {
                "field": "category_id",
                "values": [
                    {"value": cat_id, "label": "Electronics", "count": 5},
                    {"value": str(uuid4()), "label": "Clothing", "count": 3},
                ],
            }
        ]
    })

    response = client.get("/api/v1/catalog/facets")

    assert response.status_code == 200
    data = response.json()
    assert "facets" in data
    assert len(data["facets"]) >= 1
    for facet in data["facets"]:
        for val in facet["values"]:
            assert "count" in val


def test_invalid_sort_returns_400(client, fake_b2b):
    response = client.get("/api/v1/catalog/products", params={"sort": "random_garbage"})

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_SORT"


def test_b2b_unavailable_returns_502(client, fake_b2b):
    fake_b2b.catalog_unavailable = True

    response = client.get("/api/v1/catalog/products")

    assert response.status_code == 502
    assert response.json()["code"] == "B2B_UNAVAILABLE"
