import pytest

from conftest import STOCK
from tulsi_theme import palette, store


def test_stock_themes_load_and_have_credits():
    themes = store.themes()
    assert "tulsi-leaf" in themes and "catppuccin" in themes
    assert len(themes) >= 10
    for t in themes.values():
        assert t.stock
        credits = (t.path / "CREDITS.md").read_text()
        assert "Background" in credits
        # Palettes that are someone's scheme credit them and Omarchy.
        if t.slug != "tulsi-leaf":
            assert "MIT" in credits and "Omarchy" in credits, t.slug


def test_stock_themes_are_readable():
    for t in store.themes().values():
        p = t.palette
        assert palette.contrast(p["foreground"], p["background"]) >= 4.5, t.slug
        assert palette.contrast(p["accent"], p["background"]) >= 2.4, t.slug


def test_no_omarchy_wallpapers_shipped():
    assert not list(STOCK.glob("*/backgrounds/*")), "stock backgrounds need a licence and credit first"


def test_missing_keys_are_named():
    with pytest.raises(palette.PaletteError, match="missing .*accent"):
        palette.parse('mode = "dark"\nbackground = "#000000"')


def test_bad_colour_and_mode():
    text = (STOCK / "nord" / "colors.toml").read_text()
    with pytest.raises(palette.PaletteError, match="not a #rrggbb"):
        palette.parse(text.replace('accent = "#81a1c1"', 'accent = "#81a1c"'))
    with pytest.raises(palette.PaletteError, match="mode"):
        palette.parse(text.replace('mode = "dark"', 'mode = "dim"'))


def test_colour_helpers():
    assert palette.mix("#ffffff", "#000000", 0.5) == "#808080"
    assert round(palette.contrast("#ffffff", "#000000")) == 21
    assert palette.readable_on("#1e66f5") == "#ffffff"
    assert palette.readable_on("#f9e2af") == "#000000"


def test_problems_flag_low_contrast():
    p = palette.parse((STOCK / "nord" / "colors.toml").read_text().replace('foreground = "#d8dee9"', 'foreground = "#3b4252"'))
    assert any("foreground" in problem for problem in p.problems())


def test_user_theme_overrides_stock(home):
    d = store.user_themes_dir() / "nord"
    d.mkdir(parents=True)
    (d / "colors.toml").write_text((STOCK / "nord" / "colors.toml").read_text().replace("#81a1c1", "#ff0000", 1))
    t = store.get("nord")
    assert not t.stock and t.palette["accent"] == "#ff0000"


def test_state_and_undo_history():
    assert store.current() == ("tulsi-leaf", 0)
    store.record("nord", 0)
    store.record("catppuccin", 1)
    assert store.current() == ("catppuccin", 1)
    assert store.pop_previous() == ("nord", 0)
    assert store.current() == ("nord", 0)
    # Before the first switch: the desktop's own look.
    assert store.pop_previous() == (None, 0)
    assert store.current() == ("tulsi-leaf", 0) and store.pop_previous() is None
