"""Image guard tests (TDD §4.2, S2, S12).

The guard is a context budget enforced at the door: image tokens scale with resolution, so
an ungated 12-megapixel photo is one student consuming a slot's whole context while five
others wait.
"""

from __future__ import annotations

import io

import pytest

from orchestrator.gateway.images import (
    MAX_LONGEST_SIDE,
    MAX_UPLOAD_BYTES,
    ImageRejected,
    prepare_image,
    sniff_format,
)

PIL = pytest.importorskip("PIL", reason="Pillow ships in the bundle")


def make_image(width: int, height: int, fmt: str = "JPEG", **save_kw) -> bytes:
    from PIL import Image

    image = Image.new("RGB", (width, height), (120, 180, 60))
    buffer = io.BytesIO()
    image.save(buffer, format=fmt, **save_kw)
    return buffer.getvalue()


def test_a_normal_photo_passes_through():
    prepared = prepare_image(make_image(800, 600))
    assert prepared.format == "JPEG" and not prepared.resized
    assert (prepared.width, prepared.height) == (800, 600)


def test_a_large_photo_is_downscaled_to_the_token_cap():
    prepared = prepare_image(make_image(4032, 3024))  # a phone camera's default
    assert prepared.resized
    assert max(prepared.width, prepared.height) == MAX_LONGEST_SIDE
    assert prepared.bytes < prepared.original_bytes


def test_aspect_ratio_survives_the_downscale():
    prepared = prepare_image(make_image(2000, 1000))
    assert prepared.width / prepared.height == pytest.approx(2.0, abs=0.02)


def test_oversized_uploads_are_refused_with_advice_a_student_can_follow():
    data = b"\xff\xd8\xff" + b"\x00" * (MAX_UPLOAD_BYTES + 1)
    with pytest.raises(ImageRejected) as e:
        prepare_image(data)
    assert "MB" in str(e.value) and "camera quality" in str(e.value)


def test_non_image_uploads_are_refused():
    with pytest.raises(ImageRejected, match="JPEG, PNG or WebP"):
        prepare_image(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")


def test_empty_upload_is_refused():
    with pytest.raises(ImageRejected, match="empty"):
        prepare_image(b"")


def test_corrupt_image_is_a_message_not_a_stack_trace():
    with pytest.raises(ImageRejected, match="could not be read"):
        prepare_image(b"\xff\xd8\xff" + b"garbage" * 100)


def test_exif_is_stripped_so_location_never_reaches_the_model_or_the_logs():
    from PIL import Image

    source = make_image(600, 400)
    prepared = prepare_image(source)
    reopened = Image.open(io.BytesIO(prepared.data))
    assert not reopened.getexif(), "EXIF must not survive the guard"


def test_orientation_is_applied_before_exif_is_dropped():
    """A phone photo carries rotation in EXIF; dropping the tag without applying it is how a
    handwritten page arrives sideways and the model transcribes nonsense."""
    from PIL import Image

    image = Image.new("RGB", (400, 200), "white")
    exif = image.getexif()
    exif[274] = 6  # orientation: rotate 90°
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", exif=exif)

    prepared = prepare_image(buffer.getvalue())
    assert (prepared.width, prepared.height) == (200, 400), "rotation should have been applied"


@pytest.mark.parametrize("fmt", ["JPEG", "PNG", "WEBP"])
def test_the_three_allowed_formats_round_trip(fmt):
    prepared = prepare_image(make_image(300, 300, fmt))
    assert prepared.format == fmt


def test_format_is_sniffed_not_taken_from_the_client():
    assert sniff_format(make_image(10, 10, "PNG")) == "PNG"
    assert sniff_format(b"RIFF____NOTWEBP") is None
    assert sniff_format(b"") is None
