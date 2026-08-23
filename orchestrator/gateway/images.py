"""Image intake guard (TDD §4.2, S2, S12).

Enforced at the gateway, before an image ever reaches the selected model, because image token count
scales with resolution in a dynamic-resolution vision model: one 12-megapixel photo of a
notebook page can consume a whole slot's context, and the student who sent it is not the one
who pays — the other five in the classroom are.

The rules: JPEG/PNG/WebP only, ≤ 8 MiB on the wire, ≤ 20 megapixels / 8192 px per source
dimension before full decode, longest side downscaled to ≤ 1280 px, EXIF stripped (orientation
applied first, so a phone photo does not arrive sideways, and location metadata never reaches
the model or the logs).
"""

from __future__ import annotations

import io
import threading
import warnings
from dataclasses import dataclass

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_LONGEST_SIDE = 1280
MAX_SOURCE_PIXELS = 20_000_000
MAX_SOURCE_DIMENSION = 8192
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
#: Sniffed rather than trusting a client-supplied content type.
_MAGIC = {
    b"\xff\xd8\xff": "JPEG",
    b"\x89PNG\r\n\x1a\n": "PNG",
    b"RIFF": "WEBP",  # RIFF....WEBP; confirmed below
}
_PREPARE_SLOTS = threading.BoundedSemaphore(2)


class ImageRejected(ValueError):
    """Rejected at the door. The message is shown to a student, so it says what to do."""


@dataclass
class PreparedImage:
    data: bytes
    format: str
    width: int
    height: int
    original_bytes: int
    resized: bool

    @property
    def bytes(self) -> int:
        return len(self.data)


def sniff_format(data: bytes) -> str | None:
    for magic, name in _MAGIC.items():
        if data.startswith(magic):
            if name == "WEBP":
                return "WEBP" if data[8:12] == b"WEBP" else None
            return name
    return None


def _prepare_image(data: bytes, *, max_side: int = MAX_LONGEST_SIDE) -> PreparedImage:
    """Validate, orient, downscale and strip metadata. Raises `ImageRejected`."""
    if not data:
        raise ImageRejected("that upload was empty — try taking the photo again")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ImageRejected(
            f"that photo is {len(data) / 2**20:.1f} MB; please send one under "
            f"{MAX_UPLOAD_BYTES // 2**20} MB (most phones can lower the camera quality)"
        )
    fmt = sniff_format(data)
    if fmt not in ALLOWED_FORMATS:
        raise ImageRejected("please send a JPEG, PNG or WebP photo")

    try:
        from PIL import Image, ImageOps
    except ImportError:  # pragma: no cover - Pillow ships in the bundle
        raise ImageRejected("image processing is unavailable — ask the host to restart Muta")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(io.BytesIO(data))
            width, height = image.size
            if (
                width < 1
                or height < 1
                or width > MAX_SOURCE_DIMENSION
                or height > MAX_SOURCE_DIMENSION
                or width * height > MAX_SOURCE_PIXELS
            ):
                raise ImageRejected(
                    "that photo has too many pixels — resize it below 20 megapixels and retry"
                )
            # exif_transpose loads and copies the full raster, so the pixel check must happen
            # first. A highly-compressed solid PNG can otherwise expand by hundreds of MiB.
            image = ImageOps.exif_transpose(image)  # apply orientation before dropping EXIF
    except ImageRejected:
        raise
    except (Image.DecompressionBombWarning, Image.DecompressionBombError) as e:
        raise ImageRejected(
            "that photo has too many pixels — resize it below 20 megapixels and retry"
        ) from e
    except Exception as e:  # a corrupt upload is a message, not a stack trace
        raise ImageRejected("that photo could not be read — try taking it again") from e

    original = (image.width, image.height)
    if max(image.size) > max_side:
        ratio = max_side / max(image.size)
        image = image.resize((max(1, int(image.width * ratio)), max(1, int(image.height * ratio))))

    buffer = io.BytesIO()
    if fmt == "JPEG":
        image.convert("RGB").save(buffer, format="JPEG", quality=88, optimize=True)
    else:
        # Re-saving without an exif/icc chunk is how the metadata gets stripped: Pillow only
        # writes what it is handed.
        image.save(buffer, format=fmt)
    return PreparedImage(
        data=buffer.getvalue(),
        format=fmt,
        width=image.width,
        height=image.height,
        original_bytes=len(data),
        resized=(image.width, image.height) != original,
    )


def prepare_image(data: bytes, *, max_side: int = MAX_LONGEST_SIDE) -> PreparedImage:
    """Bound full-raster decode/copy work to two concurrent classroom uploads."""
    with _PREPARE_SLOTS:
        return _prepare_image(data, max_side=max_side)
