"""Web apps: websites as menu apps in their own Brave Origin window (ADR 0036).

Writes the launchers Mint's Web App Manager writes (~/.local/share/applications/
WebApp-NAME.desktop, an isolated browser profile under ~/.local/share/ice), so Web
App Manager lists, edits and removes them too. The Software Center's suggestions
(webapps.json) and `tulsi-webapp` use this.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import shutil
import string
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

# Chromium-based browsers, best first; the name is what Web App Manager calls it
# (X-WebApp-Browser), so it can edit the app later.
BROWSERS = [
    ("brave-origin", "Brave Origin"),
    ("chromium", "Chromium"),
    ("google-chrome-stable", "Chrome"),
]
CATEGORIES = ("WebApps", "Network", "Utility", "Game", "Graphics", "Office",
              "AudioVideo", "Development", "Education")
FALLBACK_ICON = "webapp-manager"


@dataclass
class Suggestion:
    name: str
    url: str
    blurb: str
    category: str = "WebApps"


@dataclass
class WebApp:
    path: Path
    name: str
    url: str


def data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")


def apps_dir() -> Path:
    return data_home() / "applications"


def ice_dir() -> Path:
    return data_home() / "ice"


def suggestions(text: str | None = None) -> list[Suggestion]:
    if text is None:
        text = resources.files(__package__).joinpath("webapps.json").read_text()
    return [Suggestion(**s) for s in json.loads(text)["apps"]]


def normalize(url: str) -> str:
    url = url.strip()
    if "://" not in url:
        url = "https://" + url
    return url


def same_site(a: str, b: str) -> bool:
    pa, pb = urllib.parse.urlsplit(normalize(a)), urllib.parse.urlsplit(normalize(b))
    host = lambda p: (p.hostname or "").removeprefix("www.")  # noqa: E731
    return host(pa) == host(pb) and pa.path.rstrip("/") == pb.path.rstrip("/")


def find_browser(which=None) -> tuple[str, str] | None:
    which = which or shutil.which
    for program, name in BROWSERS:
        if which(program):
            return program, name
    return None


def codename_for(name: str, taken: set[str], rng: random.Random | None = None) -> str:
    """As Web App Manager names them: the name's letters plus four digits."""
    rng = rng or random.Random()
    letters = "".join(filter(str.isalpha, name)) or "WebApp"
    while True:
        code = letters + "".join(rng.choice(string.digits) for _ in range(4))
        if code not in taken:
            return code


def desktop_entry(name: str, url: str, codename: str, icon: str, category: str,
                  browser: tuple[str, str], profiles: Path) -> str:
    program, browser_name = browser
    profile = profiles / codename
    exec_line = (f'{program} --app="{url}" --class=WebApp-{codename} '
                 f"--name=WebApp-{codename} --user-data-dir={profile}")
    return "\n".join([
        "[Desktop Entry]",
        "Version=1.0",
        f"Name={name}",
        "Comment=Web App",
        f"Exec={exec_line}",
        "Terminal=false",
        "X-MultipleArgs=false",
        "Type=Application",
        f"Icon={icon}",
        f"Categories=GTK;{category};",
        "MimeType=text/html;text/xml;application/xhtml_xml;",
        f"StartupWMClass=WebApp-{codename}",
        "StartupNotify=true",
        f"X-WebApp-Browser={browser_name}",
        f"X-WebApp-URL={url}",
        "X-WebApp-CustomParameters=",
        "X-WebApp-Navbar=false",
        "X-WebApp-PrivateWindow=false",
        "X-WebApp-Isolated=true",
        "",
    ])


def installed(directory: Path | None = None) -> list[WebApp]:
    directory = directory or apps_dir()
    found = []
    if not directory.is_dir():
        return found
    for path in sorted(directory.glob("*.desktop")):
        if not path.name.lower().startswith("webapp-"):
            continue
        fields = {}
        for line in path.read_text(errors="replace").splitlines():
            key, sep, value = line.partition("=")
            if sep and key not in fields:
                fields[key] = value
        if "X-WebApp-URL" in fields:
            found.append(WebApp(path, fields.get("Name", path.stem), fields["X-WebApp-URL"]))
    return found


def find(url: str, directory: Path | None = None) -> WebApp | None:
    return next((a for a in installed(directory) if same_site(a.url, url)), None)


# The site's own icon: apple-touch-icon (large) first, then icon links, then
# /favicon.ico. Only the site being added is contacted.
_LINK = re.compile(r"<link\b[^>]*>", re.I)
_ATTR = re.compile(r"""(\w[\w-]*)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""")


def icon_candidates(html: str, base: str) -> list[str]:
    ranked = []
    for tag in _LINK.findall(html):
        attrs = {m.group(1).lower(): m.group(2) or m.group(3) or m.group(4) or ""
                 for m in _ATTR.finditer(tag)}
        rel = attrs.get("rel", "").lower().split()
        href = attrs.get("href")
        if not href:
            continue
        if "apple-touch-icon" in rel or "apple-touch-icon-precomposed" in rel:
            ranked.append((0, href))
        elif "icon" in rel:
            ranked.append((1 if href.endswith((".svg", ".png")) else 2, href))
    ranked.sort(key=lambda r: r[0])
    urls = [urllib.parse.urljoin(base, h) for _, h in ranked]
    root = "{0.scheme}://{0.netloc}/favicon.ico".format(urllib.parse.urlsplit(base))
    return urls + [root]


def _suffix(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG"):
        return ".png"
    if data[:4] in (b"\x00\x00\x01\x00",):
        return ".ico"
    head = data[:512].lstrip().lower()
    if head.startswith(b"<svg") or (head.startswith(b"<?xml") and b"<svg" in data[:2048].lower()):
        return ".svg"
    return None


def _get(url: str, limit: int = 2_000_000) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"})
    with urllib.request.urlopen(request, timeout=8) as response:
        return response.read(limit)


def fetch_icon(url: str, codename: str, icons: Path, get=None) -> str:
    """Saves the site's icon as ICONS/CODENAME.EXT and returns its path, or the
    generic web app icon when there is none."""
    get = get or _get
    try:
        html = get(url).decode("utf-8", errors="replace")
    except Exception:
        html = ""
    for candidate in icon_candidates(html, url):
        try:
            data = get(candidate)
        except Exception:
            continue
        suffix = _suffix(data)
        if suffix:
            icons.mkdir(parents=True, exist_ok=True)
            path = icons / f"{codename}{suffix}"
            path.write_bytes(data)
            return str(path)
    return FALLBACK_ICON


def add(name: str, url: str, category: str = "WebApps", icon: str | None = None,
        which=None, get=None) -> WebApp:
    url = normalize(url)
    if category not in CATEGORIES:
        raise ValueError(f"unknown category {category!r}: one of {', '.join(CATEGORIES)}")
    existing = find(url)
    if existing:
        return existing
    browser = find_browser(which)
    if browser is None:
        raise RuntimeError("No Chromium-based browser is installed (Brave Origin, Chromium or Chrome).")
    directory = apps_dir()
    directory.mkdir(parents=True, exist_ok=True)
    taken = {p.stem.split("-", 1)[-1] for p in directory.glob("*.desktop")}
    codename = codename_for(name, taken)
    if icon is None:
        icon = fetch_icon(url, codename, ice_dir() / "icons", get)
    profiles = ice_dir() / "profiles"
    profiles.mkdir(parents=True, exist_ok=True)
    path = directory / f"WebApp-{codename}.desktop"
    path.write_text(desktop_entry(name, url, codename, icon, category, browser, profiles))
    return WebApp(path, name, url)


def remove(app: WebApp) -> None:
    """Removes the launcher, its profile (the site's cookies and logins) and icon."""
    codename = app.path.stem.split("-", 1)[-1]
    shutil.rmtree(ice_dir() / "profiles" / codename, ignore_errors=True)
    for icon in (ice_dir() / "icons").glob(f"{codename}.*"):
        icon.unlink(missing_ok=True)
    app.path.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tulsi-webapp",
        description="Websites as menu apps, each in its own browser window and profile.")
    sub = parser.add_subparsers(dest="command", required=True)
    p_add = sub.add_parser("add", help="add a web app to the menu")
    p_add.add_argument("name")
    p_add.add_argument("url")
    p_add.add_argument("--category", default="WebApps", choices=CATEGORIES)
    p_add.add_argument("--icon", help="an icon name or file (default: the site's own icon)")
    sub.add_parser("list", help="list the web apps")
    p_rm = sub.add_parser("remove", help="remove a web app, with its cookies and logins")
    p_rm.add_argument("url_or_name")
    sub.add_parser("suggestions", help="the Software Center's suggested web apps")
    args = parser.parse_args(argv)

    try:
        if args.command == "add":
            app = add(args.name, args.url, args.category, args.icon)
            print(app.path)
        elif args.command == "list":
            for app in installed():
                print(f"{app.name}\t{app.url}\t{app.path}")
        elif args.command == "remove":
            key = args.url_or_name
            app = next((a for a in installed() if a.name == key), None) or find(key)
            if app is None:
                print(f"tulsi-webapp: no web app {key!r}", file=sys.stderr)
                return 1
            remove(app)
        elif args.command == "suggestions":
            for s in suggestions():
                print(f"{s.name}\t{s.url}\t{s.blurb}")
    except (RuntimeError, ValueError) as e:
        print(f"tulsi-webapp: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
