"""The Calamares job `tulsios-online` (ADR 0020): SonicDE installs from the TulsiOS
cache, so without it the job stops before anything is written to the disk."""

import http.server
import importlib.util
import pathlib
import sys
import threading
import types

import pytest

JOB = pathlib.Path(__file__).resolve().parents[3] / "installer/calamares/modules/tulsios-online/main.py"
pytestmark = pytest.mark.skipif(not JOB.exists(), reason="needs the TulsiOS source tree")


def load_job(desktop, url, extras=""):
    calamares = types.ModuleType("libcalamares")
    answers = {"packagechooser_packagechooser": desktop, "packagechooser_extras": extras}
    calamares.globalstorage = types.SimpleNamespace(value=answers.get)
    calamares.job = types.SimpleNamespace(configuration={"url": url})
    calamares.utils = types.SimpleNamespace(
        gettext_path=lambda: None, gettext_languages=lambda: ["en"], debug=lambda message: None
    )
    sys.modules["libcalamares"] = calamares
    spec = importlib.util.spec_from_file_location("tulsios_online", JOB)
    job = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(job)
    return job


@pytest.fixture
def cache():
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"StoreDir: /nix/store\n")

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/nix-cache-info"
    server.shutdown()


# A port nothing listens on: the connection is refused at once.
UNREACHABLE = "http://127.0.0.1:9/nix-cache-info"


def test_sonic_with_the_cache_goes_on(cache):
    assert load_job("sonic", cache).run() is None


def test_sonic_without_the_cache_stops_before_the_disk():
    title, message = load_job("sonic", UNREACHABLE).run()
    assert "SonicDE" in title and "internet" in title
    assert "Nothing has been written to the disk" in message
    assert UNREACHABLE in message


@pytest.mark.parametrize("desktop", ["ocimum", "dwm", None])
def test_desktops_on_the_iso_need_no_cache(desktop):
    assert load_job(desktop, UNREACHABLE).run() is None


def test_ocimum_alone_needs_no_connection():
    assert load_job("ocimum", UNREACHABLE).run() is None


def test_libreoffice_needs_the_cache(cache):
    assert load_job("ocimum", cache, extras="libreoffice").run() is None
    title, message = load_job("dwm", UNREACHABLE, extras="libreoffice").run()
    assert "LibreOffice" in title and "internet" in title
    assert "Nothing has been written to the disk" in message


def test_microsoft_fonts_need_the_cache():
    title, _message = load_job("ocimum", UNREACHABLE, extras="msfonts").run()
    assert "Microsoft fonts" in title


def test_bottles_and_lutris_need_the_cache_too():
    title, _message = load_job("ocimum", UNREACHABLE, extras="bottles,lutris").run()
    assert "Bottles" in title and "Lutris" in title


def test_sonic_and_libreoffice_are_named_together():
    title, _message = load_job("sonic", UNREACHABLE, extras=["libreoffice"]).run()
    assert "SonicDE" in title and "LibreOffice" in title
