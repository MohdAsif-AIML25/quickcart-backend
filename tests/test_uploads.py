"""Product image upload: type checks, size limit, and safe file names."""

from collections.abc import Callable
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import get_settings

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
WEBP = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 64


def _upload(client: TestClient, headers: dict, product_id: int, name: str, data: bytes, mime: str):
    return client.post(
        f"/admin/products/{product_id}/image",
        files={"file": (name, data, mime)},
        headers=headers,
    )


def test_upload_valid_images(
    client: TestClient, admin_headers: dict, create_product: Callable[..., dict]
) -> None:
    product = create_product()
    cases = [
        ("a.png", PNG, "image/png", ".png"),
        ("a.jpg", JPEG, "image/jpeg", ".jpg"),
        ("a.webp", WEBP, "image/webp", ".webp"),
    ]

    for name, data, mime, extension in cases:
        response = _upload(client, admin_headers, product["id"], name, data, mime)

        assert response.status_code == 200, response.text
        image_url = response.json()["image_url"]
        assert image_url.startswith("/uploads/products/") and image_url.endswith(extension)
        # The stored file is served back with exactly the bytes we sent
        served = client.get(image_url)
        assert served.status_code == 200
        assert served.content == data


def test_upload_ignores_the_client_file_name(
    client: TestClient, admin_headers: dict, create_product: Callable[..., dict]
) -> None:
    """A path-traversal name such as ../../app/main.py must never reach the disk."""
    product = create_product()

    response = _upload(client, admin_headers, product["id"], "../../app/main.png", PNG, "image/png")

    assert response.status_code == 200
    stored_name = Path(response.json()["image_url"]).name
    assert "main" not in stored_name and ".." not in response.json()["image_url"]
    assert (get_settings().upload_dir / "products" / stored_name).is_file()


def test_text_file_renamed_to_png_is_rejected(
    client: TestClient, admin_headers: dict, create_product: Callable[..., dict]
) -> None:
    """The client controls the name and Content-Type, so we check the real bytes."""
    product = create_product()

    response = _upload(client, admin_headers, product["id"], "fake.png", b"just some text", "image/png")

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_media_type"


def test_gif_is_rejected(
    client: TestClient, admin_headers: dict, create_product: Callable[..., dict]
) -> None:
    product = create_product()

    response = _upload(client, admin_headers, product["id"], "a.gif", b"GIF89a" + b"\x00" * 32, "image/gif")

    assert response.status_code == 415


def test_file_over_the_size_limit_is_rejected(
    client: TestClient, admin_headers: dict, create_product: Callable[..., dict]
) -> None:
    product = create_product()
    too_big = PNG + b"\x00" * (get_settings().max_image_size_mb * 1024 * 1024)

    response = _upload(client, admin_headers, product["id"], "big.png", too_big, "image/png")

    assert response.status_code == 413


def test_empty_file_is_rejected(
    client: TestClient, admin_headers: dict, create_product: Callable[..., dict]
) -> None:
    product = create_product()

    assert _upload(client, admin_headers, product["id"], "empty.png", b"", "image/png").status_code == 400


def test_upload_requires_admin_and_existing_product(
    client: TestClient, admin_headers: dict, user_headers: dict, create_product: Callable[..., dict]
) -> None:
    product = create_product()

    assert _upload(client, user_headers, product["id"], "a.png", PNG, "image/png").status_code == 403
    assert _upload(client, admin_headers, 9999, "a.png", PNG, "image/png").status_code == 404
