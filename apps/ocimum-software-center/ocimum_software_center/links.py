"""Browser extensions from their store pages' links (ADR 0018).

A Chrome Web Store link carries the extension's id. A Firefox Add-ons link carries
the add-on's name in the URL ("slug"); its id comes from addons.mozilla.org's API,
which needs a network connection.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request

AMO_API = "https://addons.mozilla.org/api/v5/addons/addon/{}/"

_CHROME_ID = re.compile(r"^[a-p]{32}$")
_CHROME_HOSTS = ("chromewebstore.google.com", "chrome.google.com")
_FIREFOX_HOSTS = ("addons.mozilla.org",)


class LinkError(ValueError):
    """Not a link to an extension TulsiOS can add."""


def parse_extension_link(url: str) -> tuple[str, str, bool]:
    """(browser, id or slug, whether it still needs looking up) for a store link.

    https://chromewebstore.google.com/detail/ublock-origin/cjpalhdlnbpafiamejdnhcphjbkeiagm
        -> ("chromium", "cjpalhdlnbpafiamejdnhcphjbkeiagm", False)
    https://addons.mozilla.org/en-US/firefox/addon/ublock-origin/
        -> ("firefox", "ublock-origin", True)
    """
    text = url.strip()
    if "://" not in text:
        text = "https://" + text
    parts = urllib.parse.urlparse(text)
    host = (parts.hostname or "").lower()
    segments = [urllib.parse.unquote(s) for s in parts.path.split("/") if s]
    if host in _CHROME_HOSTS:
        for segment in reversed(segments):
            if _CHROME_ID.match(segment):
                return "chromium", segment, False
        raise LinkError("This Chrome Web Store link has no extension id in it.")
    if host in _FIREFOX_HOSTS:
        if "addon" in segments:
            i = segments.index("addon")
            if i + 1 < len(segments):
                return "firefox", segments[i + 1], True
        raise LinkError("This Firefox Add-ons link does not point at an add-on.")
    raise LinkError(
        "Paste a link to an extension's page on addons.mozilla.org or the Chrome Web Store."
    )


def firefox_extension_id(slug: str, timeout: float = 20) -> str:
    """The add-on's id (e.g. uBlock0@raymondhill.net), from addons.mozilla.org."""
    url = AMO_API.format(urllib.parse.quote(slug, safe=""))
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as reply:
            data = json.load(reply)
    except OSError as e:
        raise LinkError(f"Could not reach addons.mozilla.org: {e}") from e
    except ValueError as e:
        raise LinkError(f"Unexpected answer from addons.mozilla.org: {e}") from e
    guid = data.get("guid") if isinstance(data, dict) else None
    if not guid:
        raise LinkError(f"addons.mozilla.org does not know the add-on “{slug}”.")
    return guid
