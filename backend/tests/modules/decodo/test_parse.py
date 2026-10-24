from app.modules.decodo.parse import amazon_document, walmart_document


def test_amazon_extracts_text_images_and_category():
    result = {
        "asin": "B123456789",
        "asin_in_url": "B123456789",
        "title": "Cork coaster",
        "bullet_points": "one\ntwo",
        "description": "<p>useful</p>",
        "images": ["https://example.com/a.jpg", "https://example.com/b.jpg"],
        "category": [{"ladder": [{"name": "Home"}, {"name": "Coasters"}]}],
        "product_details": {"material_type": "Cork", "best_sellers_rank": "123"},
    }
    doc = amazon_document(result, "B123456789")
    assert doc.bullet_points == ["one", "two"]
    assert doc.category_path == ["Home", "Coasters"]
    assert doc.main_image == "https://example.com/a.jpg"
    assert doc.gallery_images == ["https://example.com/b.jpg"]
    assert "best_sellers_rank" not in doc.attributes


def test_walmart_extracts_specs_and_url_id():
    doc = walmart_document(
        {
            "general": {
                "meta": {"sku": "123"},
                "title": "Cork coaster",
                "url": "https://www.walmart.com/ip/name/123",
                "description": "<ul><li>A</li><li>B</li></ul>",
                "images": [],
            },
            "specifications": [{"key": "Material", "value": "Cork"}],
            "breadcrumbs": [{"category_name": "Home"}],
        },
        "123",
        "sku-uuid",
    )
    assert doc.attributes["Material"] == "Cork"
    assert doc.item_id == "123"
    assert "A" in (doc.description or "")
