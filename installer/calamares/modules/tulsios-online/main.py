#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Runs first, before anything is written to the disk (ADR 0020, 0032). The ISO
# installs Ocimum Desktop and dwm from itself; SonicDE, and the extra software
# ticked on the installer's last page (LibreOffice), are downloaded from the TulsiOS
# cache during the installation. Without a connection to that cache, stop here with
# a clear message, rather than after partitioning or by compiling for hours.

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

# What the ISO does not carry: it comes from the cache.
ONLINE_DESKTOPS = {"sonic": "SonicDE"}
ONLINE_EXTRAS = {"libreoffice": "LibreOffice"}


def online_choices():
    """The names of the chosen things that need the cache."""
    desktop = libcalamares.globalstorage.value("packagechooser_packagechooser") or "ocimum"
    names = [ONLINE_DESKTOPS[desktop]] if desktop in ONLINE_DESKTOPS else []
    ticked = libcalamares.globalstorage.value("packagechooser_extras") or []
    if isinstance(ticked, str):
        ticked = ticked.split(",")
    names += [ONLINE_EXTRAS[t.strip()] for t in ticked if t and t.strip() in ONLINE_EXTRAS]
    return names


def pretty_name():
    return _("Checking the connection to the TulsiOS package cache.")


def reachable(url, timeout=15):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as reply:
            return 200 <= reply.status < 400
    except (urllib.error.URLError, OSError, ValueError):
        return False


def run():
    names = online_choices()
    if not names:
        return None
    name = _(" and ").join(names)
    url = libcalamares.job.configuration.get("url", "https://cache.skarptech.org/tulsi/nix-cache-info")
    if reachable(url):
        libcalamares.utils.debug("tulsios-online: {} answers".format(url))
        return None
    return (
        _("{} needs an internet connection").format(name),
        _("{} is downloaded from the TulsiOS package cache during the installation, and "
          "the cache cannot be reached ({}). Nothing has been written to the disk. Connect "
          "to the internet and start the installation again, or go back and choose what "
          "installs from this USB stick: Ocimum Desktop or dwm, without extra "
          "software.").format(name, url),
    )
