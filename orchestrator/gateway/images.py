"""Image intake guard (TDD §4.2, S2, S12).

Enforced at the gateway, before an image ever reaches CORE-VISION, because image token count
scales with resolution in a dynamic-resolution vision model: one 12-megapixel photo of a
notebook page can consume a whole slot's context, and the student who sent it is not the one
who pays — the other five in the classroom are.

The rules: JPEG/PNG/WebP only, ≤ 8 MiB on the wire, longest side downscaled to ≤ 1280 px,
EXIF stripped (orientation applied first, so a phone photo does not arrive sideways, and
location metadata never reaches the model or the logs).
"""

from __future__ import annotations

import io
from dataclasses import dataclass

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_LONGEST_SIDE = 1280
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
#: Sniffed rather than trusting a client-supplied content type.
_MAGIC = {
    b"\xff\xd8\xff": "JPEG",
    b"\x89PNG\r\n\x1a\n": "PNG",
    b"RIFF": "WEBP",  # RIFF....WEBP; confirmed below
}


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


def prepare_image(data: bytes, *, max_side: int = MAX_LONGEST_SIDE) -> PreparedImage:
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
        # No Pillow: pass the bytes through rather than refuse the feature, but say so — an
        # unresized image is a context risk, not a correctness one.
        return PreparedImage(data, fmt, 0, 0, len(data), resized=False)

    try:
        image = Image.open(io.BytesIO(data))
        image = ImageOps.exif_transpose(image)  # apply orientation before dropping EXIF
    except Exception as e:  # noqa: BLE001 — a corrupt upload is a message, not a stack trace
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
