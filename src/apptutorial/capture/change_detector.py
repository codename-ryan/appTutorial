"""Local screen-change detection via a cheap perceptual (average) hash.

Gates the expensive vision verification call: we fingerprint the target window locally and
only call the AI once the screen has actually changed and settled - frames are never streamed
to the API. See SPEC.md §6. Thresholds are tunable.
"""

from __future__ import annotations

import io

from PIL import Image

_SIZE = 32  # 32x32 grayscale -> 1024-bit average hash
CHANGE_BITS = 30  # >= this many differing bits vs the baseline => the screen changed
STABLE_BITS = 14  # < this many differing bits vs the previous frame => the screen settled


def fingerprint(png_bytes: bytes) -> list[int]:
    """Average-hash a PNG: downscale to grayscale and threshold each pixel against the mean."""
    image = Image.open(io.BytesIO(png_bytes)).convert("L").resize((_SIZE, _SIZE))
    pixels = image.tobytes()  # mode "L" -> one 0..255 byte per pixel
    avg = sum(pixels) / len(pixels)
    return [1 if p >= avg else 0 for p in pixels]


def difference(a: list[int] | None, b: list[int] | None) -> int:
    """Hamming distance between two fingerprints (large number if either is missing)."""
    if not a or not b or len(a) != len(b):
        return 10**9
    return sum(x != y for x, y in zip(a, b, strict=True))


def changed(baseline: list[int] | None, current: list[int] | None) -> bool:
    return difference(baseline, current) >= CHANGE_BITS


def settled(previous: list[int] | None, current: list[int] | None) -> bool:
    return difference(previous, current) < STABLE_BITS
