#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Runs first, before anything is written to the disk (ADR 0020). The ISO installs
# Ocimum Desktop and dwm from itself; SonicDE it downloads from the TulsiOS cache
# during the installation. Without a connection to that cache, stop here with a
# clear message, rather than after partitioning or by compiling SonicDE for hours.

import gettext
import urllib.error
import urllib.request

import libcalamares

_ = gettext.translation(
    "calamares-python",
    localedir=libcalamares.utils.gettext_path(),
    languages=libcalamares.utils.gettext_languages(),
    fallback=True,
).gettext

# Desktops the ISO does not carry: they come from the cache.
ONLINE_DESKTOPS = {"sonic": "SonicDE"}


def pretty_name():
    return _("Checking the connection to the TulsiOS package cache.")


def reachable(url, timeout=15):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as reply:
            return 200 <= reply.status < 400
    except (urllib.error.URLError, OSError, ValueError):
        return False


def run():
    desktop = libcalamares.globalstorage.value("packagechooser_packagechooser") or "ocimum"
    name = ONLINE_DESKTOPS.get(desktop)
    if name is None:
        return None
    url = libcalamares.job.configuration.get("url", "https://cache.skarptech.org/tulsi/nix-cache-info")
    if reachable(url):
        libcalamares.utils.debug("tulsios-online: {} answers".format(url))
        return None
    return (
        _("{} needs an internet connection").format(name),
        _("{} is downloaded from the TulsiOS package cache during the installation, and "
          "the cache cannot be reached ({}). Nothing has been written to the disk. Connect "
          "to the internet and start the installation again, or choose Ocimum Desktop or "
          "dwm, which install from this USB stick.").format(name, url),
    )
