"""Mint-Y recoloured from a palette. The rewriting is tested on its own; the
compile needs libsass and Mint-Y's sources (the Nix build provides both)."""

import pytest

from conftest import mint_available
from tulsi_theme import mint, store

SAMPLE = """$base_color: null;
$bg_color: null;
@if $variant == 'light' {
    $base_color: #FFFFFF;
    $bg_color: lighten(#EBEBED, 5%);
    @if $nested { $x: 1; }
} @else {
    $base_color: #333339;
    $bg_color: lighten(#222226, 5%);
}
$accent_color: #35A854;
"""


def test_keep_variant_takes_one_branch():
    dark = mint.keep_variant(SAMPLE, dark=True)
    assert "#333339" in dark and "#FFFFFF" not in dark and "@else" not in dark
    light = mint.keep_variant(SAMPLE, dark=False)
    assert "#FFFFFF" in light and "@if $nested { $x: 1; }" in light and "#333339" not in light


def test_set_vars_replaces_every_assignment():
    text = mint.set_vars(mint.keep_variant(SAMPLE, True), {"bg_color": "#1a1b26", "accent_color": "#7aa2f7"})
    assert "$bg_color: #1a1b26;" in text and "lighten(#222226" not in text
    assert "$accent_color: #7aa2f7;" in text
    with pytest.raises(mint.MintError, match="no \\$nope"):
        mint.set_vars(text, {"nope": "#000000"})


@pytest.mark.skipif(not mint_available(), reason="needs libsass and Mint-Y (TULSI_THEME_MINT_*)")
def test_generate_recolours_gtk_and_cinnamon(tmp_path):
    theme = store.get("tokyo-night")
    dest = mint.generate(theme.palette, theme.generated_name, tmp_path)
    gtk = (dest / "gtk-3.0" / "gtk.css").read_text().lower()
    assert "#7aa2f7" in gtk and "#35a854" not in gtk
    assert "#1a1b26" in gtk
    cinnamon = (dest / "cinnamon" / "cinnamon.css").read_text().lower()
    assert "#7aa2f7" in cinnamon and "#35a854" not in cinnamon
    assets = dest / "gtk-3.0" / "assets"
    ref = mint.mint_built(True) / "gtk-3.0" / "assets"
    for name in ("checkbox-checked-dark.png", "radio-checked-dark@2.png"):
        assert mint.png_size(assets / name) == mint.png_size(ref / name)
    assert not any("35a854" in f.read_text(errors="ignore").lower() for f in (dest / "cinnamon").rglob("*.svg"))
    # A second switch to the same palette reuses the theme.
    stamp = (dest / ".tulsi-palette").stat().st_mtime_ns
    mint.generate(theme.palette, theme.generated_name, tmp_path)
    assert (dest / ".tulsi-palette").stat().st_mtime_ns == stamp


@pytest.mark.skipif(not mint_available(), reason="needs libsass and Mint-Y (TULSI_THEME_MINT_*)")
def test_generate_light_theme(tmp_path):
    theme = store.get("flexoki-light")
    dest = mint.generate(theme.palette, theme.generated_name, tmp_path)
    gtk = (dest / "gtk-3.0" / "gtk.css").read_text().lower()
    assert "#205ea6" in gtk and "#fffcf0" in gtk
