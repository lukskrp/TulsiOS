import os
import shutil
import subprocess

import pytest

from tulsi_installer import render
from tulsi_installer.render import Choices, InvalidChoice, User


def choices(**kw):
    base = dict(desktop="dwm", hostname="box", users=[User("alice", "Alice A")], state_version="26.05")
    base.update(kw)
    return Choices(**base)


def nix_parses(text, tmp_path):
    """nix-instantiate --parse, when Nix is around (it is in the package's checks)."""
    if shutil.which("nix-instantiate") is None:
        pytest.skip("nix-instantiate not available")
    env = dict(os.environ, NIX_STATE_DIR=str(tmp_path / "state"), NIX_STORE_DIR=str(tmp_path / "store"))
    f = tmp_path / "x.nix"
    f.write_text(text)
    subprocess.run(["nix-instantiate", "--parse", str(f)], check=True, capture_output=True, env=env)


def test_uefi_dwm_configuration(tmp_path):
    text = render.configuration_nix(
        choices(timezone="Europe/Stockholm", locale="sv_SE.UTF-8", keyboard_layout="se", console_keymap="sv-latin1")
    )
    assert 'tulsi.desktop.session = "dwm";' in text
    assert "boot.loader.systemd-boot.enable = true;" in text
    assert 'networking.hostName = "box";' in text
    assert 'time.timeZone = "Europe/Stockholm";' in text
    assert 'services.xserver.xkb.layout = "se";' in text
    assert 'console.keyMap = "sv-latin1";' in text
    assert 'users.users."alice" = {' in text and 'description = "Alice A";' in text
    assert 'system.stateVersion = "26.05";' in text
    # No imports or paths: those belong to the flake (and ADR 0014 treats them as code).
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    assert "import" not in code and "./" not in code, code
    nix_parses(text, tmp_path)


def test_bios_grub_with_encrypted_boot(tmp_path):
    text = render.configuration_nix(
        choices(
            desktop="ocimum",
            boot="bios",
            bios_device="/dev/sda",
            root_is_btrfs=True,
            grub_crypt_mappers=["luks-1234"],
            luks_swap={"luks-swap": "abcd-12"},
        )
    )
    assert 'boot.loader.grub.device = "/dev/sda";' in text
    assert 'boot.loader.grub.fsIdentifier = "provided";' in text
    assert "boot.loader.grub.enableCryptodisk = true;" in text
    assert 'boot.initrd.luks.devices."luks-1234".keyFile = "/boot/crypto_keyfile.bin";' in text
    assert 'boot.initrd.luks.devices."luks-swap".device = "/dev/disk/by-uuid/abcd-12";' in text
    nix_parses(text, tmp_path)


def test_strings_are_escaped(tmp_path):
    text = render.configuration_nix(choices(users=[User("bob", 'Bob "${builtins.abort 1}" \\')]))
    assert r'description = "Bob \"\${builtins.abort 1}\" \\";' in text
    nix_parses(text, tmp_path)


@pytest.mark.parametrize(
    "kw",
    [
        dict(desktop="gnome"),
        dict(hostname="bad host"),
        dict(hostname="x;rm"),
        dict(users=[]),
        dict(users=[User("root")]),
        dict(users=[User("Alice")]),
        dict(users=[User("a"), User("a")]),
        dict(state_version="unstable"),
        dict(boot="bios"),
        dict(boot="bios", bios_device="/dev/sda; true"),
        dict(timezone='Europe/"x"'),
        dict(locale="en_US.UTF-8\n"),
        dict(extra_locale={"LANG": "C"}),
        dict(keyboard_layout='se"'),
        dict(autologin="mallory"),
        dict(grub_crypt_mappers=["luks-1"]),  # needs boot = bios
    ],
)
def test_invalid_choices_are_refused(kw):
    with pytest.raises(InvalidChoice):
        render.configuration_nix(choices(**kw))


def test_extra_locale_only_when_different():
    text = render.configuration_nix(
        choices(locale="en_US.UTF-8", extra_locale={"LC_TIME": "sv_SE.UTF-8", "LC_PAPER": "en_US.UTF-8"})
    )
    assert 'LC_TIME = "sv_SE.UTF-8";' in text
    assert "LC_PAPER" not in text


def test_flake_from_the_shared_template(tmp_path):
    template = os.environ.get("TULSI_FLAKE_TEMPLATE")
    if not template:
        pytest.skip("TULSI_FLAKE_TEMPLATE not set")
    text = render.flake_nix(open(template).read(), "/nix/store/abc-source", "box")
    assert 'inputs.tulsi.url = "path:/nix/store/abc-source";' in text
    assert 'nixosConfigurations."box"' in text
    assert '"${tulsi}/nix/hosts/desktop"' in text
    assert "hardware-configuration.nix" in text
    nix_parses(text, tmp_path)


def test_unknown_placeholder_is_an_error():
    with pytest.raises(InvalidChoice):
        render.flake_nix("@source@ @surprise@", "/s", "h")


def test_btrfs_subvolumes_fixed():
    # As nixos-generate-config writes it.
    hw = """
  fileSystems."/" =
    { device = "/dev/disk/by-uuid/1";
      fsType = "btrfs";
    };

  fileSystems."/home" =
    { device = "/dev/disk/by-uuid/1";
      fsType = "btrfs";
      options = [ "subvol=/home" ];
    };

  fileSystems."/nix" =
    { device = "/dev/disk/by-uuid/1";
      fsType = "btrfs";
      options = [ "subvol=/nix" "compress=zstd" ];
    };
"""
    out = render.fix_btrfs_subvolumes(hw)
    assert '[ "subvol=home" ]' in out, out
    assert '[ "subvol=nix" "compress=zstd" ]' in out, out
    assert out.count("subvol=") == 2


def test_unfree_kernel_modules_dropped():
    hw = "  boot.extraModulePackages = [ config.boot.kernelPackages.broadcom_sta config.boot.kernelPackages.v4l2loopback ];\n"
    assert render.extra_module_packages(hw) == ["broadcom_sta", "v4l2loopback"]
    out = render.drop_extra_module_packages(hw, ["broadcom_sta"])
    assert out == "  boot.extraModulePackages = [ config.boot.kernelPackages.v4l2loopback ];\n"
    assert "[ ];" in render.drop_extra_module_packages(hw, ["broadcom_sta", "v4l2loopback"])


KBD = """# Generated
us	us	pc105	-	terminate:ctrl_alt_bksp
sv-latin1	se	pc105	-	terminate:ctrl_alt_bksp
de-latin1-nodeadkeys	de	pc105	nodeadkeys	terminate:ctrl_alt_bksp
de	de	pc105	-	terminate:ctrl_alt_bksp
"""


def test_console_keymap_from_layout():
    assert render.console_keymap_for("se", None, KBD) == "sv-latin1"
    assert render.console_keymap_for("de", "nodeadkeys", KBD) == "de-latin1-nodeadkeys"
    assert render.console_keymap_for("us", None, KBD) is None
    assert render.console_keymap_for("xx", None, KBD) is None
