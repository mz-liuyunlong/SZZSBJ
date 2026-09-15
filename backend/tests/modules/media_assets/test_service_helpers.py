from app.modules.media_assets.service import media_object_keys


def test_media_object_keys_are_content_addressed() -> None:
    digest = "a" * 64

    thumbnail, preview = media_object_keys(digest)

    assert thumbnail == f"images/aa/{digest}/thumbnail_128.webp"
    assert preview == f"images/aa/{digest}/preview_512.webp"
