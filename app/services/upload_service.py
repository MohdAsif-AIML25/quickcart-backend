import uuid

from fastapi import UploadFile

from app.core.config import get_settings
from app.core.exceptions import BadRequestError, PayloadTooLargeError, UnsupportedMediaTypeError

ALLOWED_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
CHUNK_SIZE = 64 * 1024


def _detect_image_type(header: bytes) -> str | None:
    """Check the file's real bytes ("magic numbers"), not just its name."""
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "image/webp"
    return None


def save_product_image(file: UploadFile) -> str:
    settings = get_settings()
    max_bytes = settings.max_image_size_mb * 1024 * 1024

    if file.content_type not in ALLOWED_TYPES:
        raise UnsupportedMediaTypeError("Only JPEG, PNG and WebP images are allowed")

    data = bytearray()
    while chunk := file.file.read(CHUNK_SIZE):
        data.extend(chunk)
        if len(data) > max_bytes:
            raise PayloadTooLargeError(f"Image must be at most {settings.max_image_size_mb} MB")
    if not data:
        raise BadRequestError("Uploaded file is empty")

    detected = _detect_image_type(bytes(data[:12]))
    if detected is None:
        raise UnsupportedMediaTypeError("File content is not a valid JPEG, PNG or WebP image")

    target_dir = settings.upload_dir / "products"
    target_dir.mkdir(parents=True, exist_ok=True)
    # Never trust the user's filename (path traversal like "../../app/main.py")
    filename = f"{uuid.uuid4().hex}{ALLOWED_TYPES[detected]}"
    (target_dir / filename).write_bytes(data)
    return f"/uploads/products/{filename}"