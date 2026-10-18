import io

from PIL import Image

from apptutorial.capture.backend import WindowInfo
from apptutorial.capture.screenshot import crop_png, image_box_from_rect


def _win():
    return WindowInfo(
        hwnd=1,
        title="t",
        process_name="p",
        left=100,
        top=50,
        width=800,
        height=600,
        scale_factor=1.0,
    )


def _png(w, h):
    buffer = io.BytesIO()
    Image.new("RGB", (w, h), (10, 20, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_image_box_from_rect_converts_to_image_coords_with_margin():
    box = image_box_from_rect(_win(), 800, 600, (300, 150, 100, 40), margin_frac=0.0)
    # screen (300,150) -> image-relative (200,100); 8px fixed margin on each side.
    assert box == (192, 92, 308, 148)


def test_image_box_clamps_to_image_bounds():
    left, top, right, bottom = image_box_from_rect(_win(), 800, 600, (90, 40, 100, 40))
    assert left == 0 and top == 0
    assert right <= 800 and bottom <= 600


def test_image_box_none_when_target_offscreen():
    assert image_box_from_rect(_win(), 800, 600, (2000, 2000, 50, 50)) is None


def test_crop_png_returns_cropped_region():
    out = crop_png(_png(200, 200), (10, 10, 60, 60))
    assert out is not None
    assert Image.open(io.BytesIO(out)).size == (50, 50)


def test_crop_png_none_box_returns_none():
    assert crop_png(_png(50, 50), None) is None
