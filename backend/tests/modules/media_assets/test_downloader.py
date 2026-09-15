import httpx
import pytest

from app.modules.media_assets.downloader import (
    MediaDownloadError,
    MediaSourceDownloader,
    validate_source_url,
)


def public_resolver(_: str) -> tuple[str, ...]:
    return ("93.184.216.34",)


def test_validate_source_url_accepts_allowlisted_public_https_host() -> None:
    host = validate_source_url(
        "https://images.example.com/a.jpg",
        frozenset({"images.example.com"}),
        resolver=public_resolver,
    )

    assert host == "images.example.com"


@pytest.mark.parametrize(
    ("url", "code"),
    [
        ("http://images.example.com/a.jpg", "SOURCE_URL_NOT_ALLOWED"),
        ("https://user@images.example.com/a.jpg", "SOURCE_URL_NOT_ALLOWED"),
        ("https://other.example.com/a.jpg", "SOURCE_URL_NOT_ALLOWED"),
    ],
)
def test_validate_source_url_rejects_unsafe_urls(url: str, code: str) -> None:
    with pytest.raises(MediaDownloadError) as exc:
        validate_source_url(
            url,
            frozenset({"images.example.com"}),
            resolver=public_resolver,
        )

    assert exc.value.code == code
    assert exc.value.retryable is False


def test_validate_source_url_rejects_private_resolution() -> None:
    with pytest.raises(MediaDownloadError) as exc:
        validate_source_url(
            "https://images.example.com/a.jpg",
            frozenset({"images.example.com"}),
            resolver=lambda _: ("127.0.0.1",),
        )

    assert exc.value.code == "SOURCE_HOST_NOT_PUBLIC"


def test_download_enforces_content_type_and_size() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"content-type": "image/jpeg", "content-length": "4"},
            content=b"jpeg",
            request=request,
        )
    )
    downloader = MediaSourceDownloader(
        allowed_hosts=frozenset({"images.example.com"}),
        timeout_ms=1000,
        max_source_bytes=32,
        transport=transport,
        resolver=public_resolver,
    )

    downloaded = downloader.download("https://images.example.com/a.jpg")

    assert downloaded.data == b"jpeg"
    assert downloaded.mime_type == "image/jpeg"


def test_download_rejects_redirects() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            302,
            headers={"location": "https://other.example.com/a.jpg"},
            request=request,
        )
    )
    downloader = MediaSourceDownloader(
        allowed_hosts=frozenset({"images.example.com"}),
        timeout_ms=1000,
        max_source_bytes=32,
        transport=transport,
        resolver=public_resolver,
    )

    with pytest.raises(MediaDownloadError) as exc:
        downloader.download("https://images.example.com/a.jpg")

    assert exc.value.code == "SOURCE_REDIRECT_NOT_ALLOWED"
