from uuid import uuid4


def _product(min_price: int = 1000, category_id: str | None = None) -> dict:
    """A B2B ProductPublicShortResponse item, exactly as the list endpoint returns.

    Deliberately has NO `skus` and NO `images` array — only the Short-form fields.
    A mapper that reads those non-existent keys will produce min_price=0/has_stock=
    False/empty images and fail the schema test below.
    """
    pid = str(uuid4())
    return {
        "id": pid,
        "title": "Test Product",
        "slug": "test-product",
        "status": "MODERATED",
        "category_id": category_id or str(uuid4()),
        "min_price": min_price,
        "cover_image": "/s3/img.jpg",
        "created_at": "2026-01-01T00:00:00Z",
    }


def test_catalog_returns_filtered_sorted_products(client, fake_b2b):
    p1 = _product(min_price=500)
    p2 = _product(min_price=1500)
    fake_b2b.set_catalog_response([p1, p2])

    response = client.get("/api/v1/catalog/products", params={"sort": "price_asc"})

    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert len(data["items"]) == 2
    assert data["items"][0]["id"] == p1["id"]
    assert data["items"][1]["id"] == p2["id"]


def test_catalog_items_match_catalog_product_card_schema(client, fake_b2b):
    """Each item must conform to CatalogProductCard, built from the Short response.

    required: [id, name, min_price, has_stock, images]. Values come from the B2B
    Short fields: name<-title, min_price<-min_price, images<-cover_image. The
    fixture has no `skus`/`images` keys, so a mapper that reads them fails here.
    """
    p = _product(min_price=999)
    fake_b2b.set_catalog_response([p])

    response = client.get("/api/v1/catalog/products")

    assert response.status_code == 200
    item = response.json()["items"][0]

    # Every required field, under the spec name and type.
    assert item["id"] == p["id"]
    assert item["name"] == p["title"]
    assert item["min_price"] == 999  # taken from the Short `min_price`, not skus
    assert isinstance(item["min_price"], int)
    assert item["has_stock"] is True

    # images is an array of ImageRef objects built from the single `cover_image`
    # URL (required ImageRef fields: id, url, ordering).
    assert isinstance(item["images"], list)
    first_image = item["images"][0]
    assert isinstance(first_image, dict)
    assert first_image["url"] == p["cover_image"]
    assert "id" in first_image
    assert "ordering" in first_image

    # Legacy / off-contract names must be gone.
    for legacy in ("title", "price", "in_stock", "is_in_cart", "image"):
        assert legacy not in item


def _full_product(category_id: str, brand: str, color: str = "black") -> dict:
    """A full B2B public product (as /public/products/batch returns) with characteristics."""
    pid = str(uuid4())
    return {
        "id": pid,
        "title": "Test Product",
        "slug": "test-product",
        "status": "MODERATED",
        "category_id": category_id,
        "characteristics": [{"id": str(uuid4()), "name": "brand", "value": brand}],
        "skus": [
            {
                "id": str(uuid4()),
                "name": "base",
                "price": 1000,
                "active_quantity": 3,
                "characteristics": [{"id": str(uuid4()), "name": "color", "value": color}],
            }
        ],
    }


def test_facets_return_counts_per_filter_value(client, fake_b2b):
    """Facets are really computed from B2B characteristics, not a canned response."""
    cat_id = str(uuid4())
    products = [
        _full_product(cat_id, "Apple"),
        _full_product(cat_id, "Apple"),
        _full_product(cat_id, "Samsung"),
    ]
    for p in products:
        fake_b2b.add_product(p)
    # The public list only yields ids; the batch call yields the full cards.
    fake_b2b.set_catalog_response([{"id": p["id"]} for p in products])

    response = client.get("/api/v1/catalog/facets", params={"category_id": cat_id})

    assert response.status_code == 200
    data = response.json()
    assert "facets" in data

    brand_facet = next(f for f in data["facets"] if f["field"] == "brand")
    brand_counts = {v["value"]: v["count"] for v in brand_facet["values"]}
    assert brand_counts == {"Apple": 2, "Samsung": 1}

    # Every facet value carries a count (also covers the SKU-level "color" facet).
    for facet in data["facets"]:
        for val in facet["values"]:
            assert "count" in val


def test_facets_b2b_unavailable_returns_502(client, fake_b2b):
    fake_b2b.b2b_unavailable = True

    response = client.get("/api/v1/catalog/facets")

    assert response.status_code == 502
    assert response.json()["code"] == "B2B_UNAVAILABLE"


def test_invalid_sort_returns_400(client, fake_b2b):
    response = client.get("/api/v1/catalog/products", params={"sort": "random_garbage"})

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_SORT"


def test_b2b_unavailable_returns_502(client, fake_b2b):
    fake_b2b.catalog_unavailable = True

    response = client.get("/api/v1/catalog/products")

    assert response.status_code == 502
    assert response.json()["code"] == "B2B_UNAVAILABLE"


def test_limit_offset_pagination_accepted(client, fake_b2b):
    fake_b2b.set_catalog_response([])

    response = client.get("/api/v1/catalog/products", params={"limit": 10, "offset": 20})

    assert response.status_code == 200


def test_deep_object_filter_params_accepted(client, fake_b2b):
    from uuid import uuid4
    cat_id = str(uuid4())
    fake_b2b.set_catalog_response([])

    response = client.get(
        "/api/v1/catalog/products",
        params={"filter[category_id]": cat_id, "filter[price_min]": 100, "filter[price_max]": 5000},
    )

    assert response.status_code == 200
