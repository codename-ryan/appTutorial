import io

from PIL import Image

from apptutorial.capture.change_detector import (
    CHANGE_BITS,
    STABLE_BITS,
    changed,
    difference,
    fingerprint,
    settled,
)


def _png(pixel_fn, size=64):
    """Render a grayscale PNG from a (x, y) -> 0..255 function."""
    image = Image.new("L", (size, size))
    image.putdata([pixel_fn(i % size, i // size) for i in range(size * size)])
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_fingerprint_is_1024_bits():
    png = _png(lambda x, y: 255 if x < 32 else 0)
    assert len(fingerprint(png)) == 1024


def test_identical_images_are_settled_and_unchanged():
    fp = fingerprint(_png(lambda x, y: 255 if x < 32 else 0))
    assert difference(fp, fp) == 0
    assert settled(fp, fp)
    assert not changed(fp, fp)


def test_difference_handles_missing_fingerprints():
    fp = fingerprint(_png(lambda x, y: 255 if x < 32 else 0))
    assert difference(fp, None) >= 10**9
    assert difference(None, None) >= 10**9


def test_structurally_different_images_register_as_changed():
    vertical = fingerprint(_png(lambda x, y: 255 if x < 32 else 0))  # left/right split
    horizontal = fingerprint(_png(lambda x, y: 255 if y < 32 else 0))  # top/bottom split
    assert changed(vertical, horizontal)
    assert not settled(vertical, horizontal)


def test_changed_and_settled_thresholds():
    base = [0] * 1024
    small = [1 if i < STABLE_BITS - 1 else 0 for i in range(1024)]  # just under "settled"
    big = [1 if i < CHANGE_BITS + 5 else 0 for i in range(1024)]  # over "changed"
    assert not changed(base, small)
    assert settled(base, small)
    assert changed(base, big)
    assert not settled(base, big)
