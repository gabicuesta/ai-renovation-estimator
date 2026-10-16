"""Normalise user photos before they reach a model: size, format and count limits.

Vision tokens scale with resolution. Downscaling to ~1.5k px keeps the details that matter
for a renovation (tiles, fixtures, damp stains) at a fraction of the cost.
"""

from __future__ import annotations

import base64
import io

from PIL import Image as PILImage
from PIL import ImageOps, UnidentifiedImageError

from .providers import Image

MAX_IMAGES = 6
MAX_BYTES = 15 * 1024 * 1024
MAX_SIDE = 1568


class ImageError(ValueError):
    pass


def prepare(raw_images: list[bytes]) -> list[Image]:
    if len(raw_images) > MAX_IMAGES:
        raise ImageError(f"Up to {MAX_IMAGES} photos per estimate.")
    out = []
    for i, raw in enumerate(raw_images, start=1):
        if len(raw) > MAX_BYTES:
            raise ImageError(f"Photo {i} is larger than {MAX_BYTES // (1024 * 1024)} MB.")
        try:
            img = PILImage.open(io.BytesIO(raw))
            img = ImageOps.exif_transpose(img)  # respect phone orientation
        except (UnidentifiedImageError, OSError) as exc:
            raise ImageError(f"Photo {i} is not a valid image.") from exc
        img = img.convert("RGB")
        img.thumbnail((MAX_SIDE, MAX_SIDE))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        out.append(Image(media_type="image/jpeg", data_b64=base64.b64encode(buf.getvalue()).decode()))
    return out
