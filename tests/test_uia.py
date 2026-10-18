from apptutorial.accessibility.uia import UIElement, format_elements, is_meaningful_name


def test_is_meaningful_name_keeps_real_text():
    assert is_meaningful_name("Home")
    assert is_meaningful_name("New Tab")
    assert is_meaningful_name("100%")


def test_is_meaningful_name_rejects_glyphs_and_blanks():
    assert not is_meaningful_name("")
    assert not is_meaningful_name("   ")
    glyph = chr(0xE710)  # icon-font / private-use-area glyph, like Windows Terminal's icons
    assert not is_meaningful_name(glyph)
    assert not is_meaningful_name(glyph + glyph)


def test_format_elements_empty():
    assert "no accessibility" in format_elements([]).lower()


def test_format_elements_strips_control_suffix():
    elements = [
        UIElement("Home", "TabItemControl", 0, 0, 10, 10),
        UIElement("Bold", "ButtonControl", 0, 0, 5, 5),
    ]
    out = format_elements(elements)
    assert "Home" in out
    assert "Bold" in out
    assert "[TabItem]" in out  # "Control" suffix removed
    assert "Control" not in out


def test_format_elements_respects_limit():
    elements = [UIElement(f"e{i}", "ButtonControl", 0, 0, 1, 1) for i in range(100)]
    out = format_elements(elements, limit=10)
    assert len(out.splitlines()) == 10
