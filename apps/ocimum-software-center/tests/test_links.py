import pytest

from ocimum_software_center.links import LinkError, parse_extension_link

UBLOCK_CHROME = "cjpalhdlnbpafiamejdnhcphjbkeiagm"


def test_chrome_web_store_links_carry_the_id():
    for url in (
        f"https://chromewebstore.google.com/detail/ublock-origin/{UBLOCK_CHROME}",
        f"https://chromewebstore.google.com/detail/{UBLOCK_CHROME}?hl=en",
        f"https://chrome.google.com/webstore/detail/ublock-origin/{UBLOCK_CHROME}",
        f"chromewebstore.google.com/detail/x/{UBLOCK_CHROME}",
    ):
        assert parse_extension_link(url) == ("chromium", UBLOCK_CHROME, False)


def test_firefox_links_need_a_lookup():
    assert parse_extension_link(
        "https://addons.mozilla.org/en-US/firefox/addon/ublock-origin/"
    ) == ("firefox", "ublock-origin", True)
    assert parse_extension_link(
        "https://addons.mozilla.org/firefox/addon/dark%20reader"
    ) == ("firefox", "dark reader", True)


def test_other_links_are_refused():
    for url in (
        "https://example.com/extension",
        "https://chromewebstore.google.com/category/extensions",
        "https://addons.mozilla.org/en-US/firefox/",
    ):
        with pytest.raises(LinkError):
            parse_extension_link(url)
