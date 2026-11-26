#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# The TulsiOS install job (ADR 0016). Replaces calamares-nixos-extensions' `nixos`
# job: it hands Calamares' answers to tulsi-install-system, which writes the
# TulsiOS system flake into /etc/nixos and runs nixos-install, and turns Nix's
# log into the progress bar.
#
# The GRUB key file for encrypted /boot and NixProgress are from
# calamares-nixos-extensions (https://github.com/NixOS/calamares-nixos-extensions),
# MIT licence, Copyright (c) the calamares-nixos-extensions contributors.

import gettext
import json
import os
import subprocess
import tempfile

import libcalamares

_ = gettext.translation(
    "calamares-python",
    localedir=libcalamares.utils.gettext_path(),
    languages=libcalamares.utils.gettext_languages(),
    fallback=True,
).gettext

# The global storage keys tulsi-install-system reads (tulsi_installer/calamares.py).
KEYS = [
    "packagechooser_packagechooser",
    "packagechooser_extras",
    "hostname",
    "username",
    "fullname",
    "autoLoginUser",
    "locationRegion",
    "locationZone",
    "localeConf",
    "keyboardLayout",
    "keyboardVariant",
    "keyboardVConsoleKeymap",
    "firmwareType",
    "bootLoader",
    "partitions",
]
LUKS = ("luks", "luks2")

status = _("Installing TulsiOS")


def pretty_name():
    return _("Installing TulsiOS.")


def pretty_status_message():
    return status


def answers(gs):
    """The answers, without LUKS passphrases."""
    out = {}
    for key in KEYS:
        value = gs.value(key)
        if key == "partitions" and value:
            value = [{k: v for k, v in p.items() if k != "luksPassphrase"} for p in value]
        out[key] = value
    return out


def needs_grub_key_file(gs):
    if gs.value("firmwareType") == "efi":
        return False
    parts = gs.value("partitions") or []
    root = next((p for p in parts if p.get("mountPoint") == "/"), {})
    boot = next((p for p in parts if p.get("mountPoint") == "/boot"), None)
    if boot is not None:
        return boot.get("fsName") in LUKS
    return root.get("fsName") in LUKS


def make_grub_key_file(gs, root):
    """GRUB unlocks /boot itself; the key file spares a second passphrase prompt."""
    run = libcalamares.utils.host_env_process_output
    keyfile = root + "/boot/crypto_keyfile.bin"
    run(["mkdir", "-p", root + "/boot"], None)
    run(["chmod", "0700", root + "/boot"], None)
    run(["dd", "bs=512", "count=4", "if=/dev/random", "of=" + keyfile, "iflag=fullblock"], None)
    run(["chmod", "600", keyfile], None)
    for p in gs.value("partitions") or []:
        if p.get("claimed") is True and p.get("fsName") in LUKS and p.get("device"):
            # GRUB only reads pbkdf2 key slots in LUKS2.
            run(["cryptsetup", "luksConvertKey", "--hash", "sha256", "--pbkdf", "pbkdf2", p["device"]],
                None, p["luksPassphrase"])
            run(["cryptsetup", "luksAddKey", "--hash", "sha256", "--pbkdf", "pbkdf2", p["device"], keyfile],
                None, p["luksPassphrase"])


# nix internal-json activity/result types
_ACT_COPY_PATH = 100
_ACT_COPY_PATHS = 103
_ACT_BUILDS = 104
_RES_PROGRESS = 105


class NixProgress:
    """Parse nix internal-json output and track build/copy progress."""

    def __init__(self):
        self._per_act_progress = {}
        self._copy_bytes = {}
        self._activities = {}
        self.fraction = 0.0
        self._floor = 0.0
        self._floor_done = 0
        self.log_messages = []

    def handle(self, line):
        """Process one line. Returns True for @nix lines, False for plain text."""
        line = line.strip()
        if not line:
            return True
        if not line.startswith("@nix "):
            return False
        try:
            msg = json.loads(line[5:])
        except ValueError:
            return False
        action = msg.get("action")
        if action == "start":
            self._activities[msg["id"]] = msg.get("type", 0)
            if msg.get("text") and msg.get("level", 5) <= 3:
                self.log_messages.append(msg["text"])
        elif action == "stop":
            self._activities.pop(msg["id"], None)
            self._copy_bytes.pop(msg["id"], None)
        elif action == "result":
            self._on_result(msg)
        elif action == "msg" and msg.get("level", 0) <= 1 and msg.get("msg"):
            self.log_messages.append(msg["msg"])
        self._update()
        return True

    def _on_result(self, msg):
        act_id = msg["id"]
        fields = msg.get("fields", [])
        act_type = self._activities.get(act_id, 0)
        if msg.get("type", 0) != _RES_PROGRESS or len(fields) < 2:
            return
        if act_type == _ACT_BUILDS:
            self._per_act_progress[act_id] = (fields[0], fields[1])
        elif act_type == _ACT_COPY_PATHS:
            self._per_act_progress[act_id] = (fields[0], fields[1])
        elif act_type == _ACT_COPY_PATH:
            self._copy_bytes[act_id] = (fields[0], max(fields[1], 1))

    def _update(self):
        done = sum(d for d, _ in self._per_act_progress.values())
        total = sum(t for _, t in self._per_act_progress.values())
        if total <= 0:
            return
        effective_total = max(total, 3)
        raw = done / effective_total
        total_bytes = sum(t for _, t in self._copy_bytes.values())
        if total_bytes > 0:
            done_bytes = sum(d for d, _ in self._copy_bytes.values())
            raw += (done_bytes / total_bytes) * (len(self._copy_bytes) / effective_total)
        raw = max(0.0, min(1.0, raw))
        # When more work shows up, map it into the rest of the bar instead of going back.
        if raw >= self._floor:
            self._floor, self._floor_done = raw, done
        else:
            remaining = effective_total - self._floor_done
            if remaining > 0 and done >= self._floor_done:
                raw = self._floor + ((done - self._floor_done) / remaining) * (1.0 - self._floor)
                self._floor, self._floor_done = max(self._floor, raw), done
            raw = self._floor
        self.fraction = raw


def run():
    global status
    gs = libcalamares.globalstorage
    root = gs.value("rootMountPoint")
    libcalamares.job.setprogress(0.01)

    if needs_grub_key_file(gs):
        status = _("Setting up LUKS")
        try:
            make_grub_key_file(gs, root)
        except subprocess.CalledProcessError as e:
            libcalamares.utils.error("GRUB key file: {}".format(e))
            return (_("Failed to create /boot/crypto_keyfile.bin"),
                    _("Check if you have enough free space on your partition."))

    status = _("Writing the TulsiOS configuration")
    libcalamares.job.setprogress(0.05)
    fd, answers_file = tempfile.mkstemp(prefix="tulsios-answers-", suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump(answers(gs), f)

    status = _("Installing TulsiOS")
    libcalamares.job.setprogress(0.1)
    cmd = ["pkexec", "tulsi-install-system", "--root", root, "--calamares", answers_file, "--progress-json"]
    progress = NixProgress()
    output = []
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in proc.stdout:
            if progress.handle(line):
                libcalamares.job.setprogress(0.1 + 0.9 * progress.fraction)
                if progress.log_messages:
                    libcalamares.utils.debug("nixos-install: {}".format(progress.log_messages[-1]))
                    output.extend(progress.log_messages)
                    progress.log_messages = []
            else:
                libcalamares.utils.debug("tulsi-install-system: {}".format(line.rstrip()))
                output.append(line.rstrip())
        code = proc.wait()
    finally:
        os.unlink(answers_file)
    if code != 0:
        return (_("The installation failed"), "\n".join(output[-30:]))
    libcalamares.job.setprogress(1.0)
    return None
