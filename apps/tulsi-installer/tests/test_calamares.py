from tulsi_installer import render
from tulsi_installer.calamares import choices_from_globalstorage

KBD = "sv-latin1\tse\tpc105\t-\tterminate:ctrl_alt_bksp\n"


def gs(**kw):
    base = {
        "packagechooser_packagechooser": "dwm",
        "hostname": "tulsi-laptop",
        "username": "alice",
        "fullname": "Alice",
        "locationRegion": "Europe",
        "locationZone": "Stockholm",
        "localeConf": {"LANG": "en_US.UTF-8/UTF-8", "LC_TIME": "sv_SE.UTF-8/UTF-8"},
        "keyboardLayout": "se",
        "keyboardVariant": "",
        "firmwareType": "efi",
        "bootLoader": None,
        "partitions": [{"mountPoint": "/", "fs": "ext4", "fsName": "ext4", "claimed": True, "device": "/dev/vda2"}],
    }
    base.update(kw)
    return base


def test_uefi_install_with_dwm():
    c = choices_from_globalstorage(gs(), KBD, "26.05")
    assert c.desktop == "dwm"
    assert c.boot == "uefi" and c.bios_device is None
    assert c.timezone == "Europe/Stockholm"
    assert c.locale == "en_US.UTF-8" and c.extra_locale == {"LC_TIME": "sv_SE.UTF-8"}
    assert c.console_keymap == "sv-latin1"
    assert [u.name for u in c.users] == ["alice"] and c.autologin is None
    render.validate(c)


def test_default_desktop_is_ocimum():
    c = choices_from_globalstorage(gs(packagechooser_packagechooser=None), KBD, "26.05")
    assert c.desktop == "ocimum"


def test_sonic_from_the_desktop_page():
    c = choices_from_globalstorage(gs(packagechooser_packagechooser="sonic"), KBD, "26.05")
    assert c.desktop == "sonic"
    render.validate(c)


def test_bios_with_encrypted_root_gets_a_grub_key_file():
    parts = [
        {"mountPoint": "/", "fs": "btrfs", "fsName": "luks2", "claimed": True, "device": "/dev/sda2",
         "luksMapperName": "luks-root", "uuid": "1111"},
        {"mountPoint": "", "fs": "linuxswap", "fsName": "luks", "claimed": True, "device": "/dev/sda3",
         "luksMapperName": "luks-swap", "uuid": "2222"},
    ]
    c = choices_from_globalstorage(
        gs(firmwareType="bios", bootLoader={"installPath": "/dev/sda"}, partitions=parts), KBD, "26.05"
    )
    assert c.boot == "bios" and c.bios_device == "/dev/sda"
    assert c.root_is_btrfs
    assert c.grub_crypt_mappers == ["luks-root", "luks-swap"]
    assert c.luks_swap == {"luks-swap": "2222"}
    render.validate(c)


def test_autologin_and_explicit_console_keymap():
    c = choices_from_globalstorage(gs(autoLoginUser="alice", keyboardVConsoleKeymap=" dvorak "), KBD, "26.05")
    assert c.autologin == "alice"
    assert c.console_keymap == "dvorak"


def test_extra_software_ticked_in_the_installer():
    assert choices_from_globalstorage(gs(), KBD, "26.05").extras == []
    for ticked in ("libreoffice", ["libreoffice"], "libreoffice,"):
        c = choices_from_globalstorage(gs(packagechooser_extras=ticked), KBD, "26.05")
        assert c.extras == ["libreoffice"], ticked
        render.validate(c)
    assert choices_from_globalstorage(gs(packagechooser_extras=""), KBD, "26.05").extras == []
    # The "Media" page: codecs unless the person picked patent-free formats.
    assert choices_from_globalstorage(gs(), KBD, "26.05").codecs
    assert choices_from_globalstorage(gs(packagechooser_media="codecs"), KBD, "26.05").codecs
    assert not choices_from_globalstorage(gs(packagechooser_media="free"), KBD, "26.05").codecs
    # Several at once (the page is optionalmultiple).
    c = choices_from_globalstorage(gs(packagechooser_extras="libreoffice,bottles,lutris"), KBD, "26.05")
    assert c.extras == ["libreoffice", "bottles", "lutris"]
    render.validate(c)
