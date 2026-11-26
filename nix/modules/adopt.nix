# tulsi.adopt — imperative installs meet the TulsiOS way (ADR 0013).
#
# - `apt`, `apt-get`, `dnf`, `yum`, `pacman`, `zypper`, `snap`, `brew` exist, and
#   explain how TulsiOS installs software (and open `tulsi-adopt` in a graphical
#   session). They always exit 1, so scripts still notice nothing was installed.
# - So do the install commands of `pip`, `pipx`, `npm -g`, `cargo`, `gem`, `go` and
#   `flatpak` (ADR 0018); their other commands run the real tool if there is one.
# - Downloaded .deb/.rpm/.AppImage/.flatpakref/archives/.run files open in `tulsi-adopt`,
#   which finds the matching TulsiOS package first (tulsid's Match, ADR 0018).
# - Programs built for other distributions: NixOS's ELF-loader stub
#   (/lib64/ld-linux-x86-64.so.2) is replaced by one that also opens `tulsi-adopt`
#   with the program, which offers to have the Assistant package it.
{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.tulsi.adopt;
  adopt = "${config.ocimum.softwareCenter.package}/bin/tulsi-adopt";

  shims = map (
    tool:
    pkgs.writeShellScriptBin tool ''
      exec ${adopt} shim ${tool} "$@"
    ''
  ) cfg.commands;

  # pip, npm, cargo, …: only installing goes to tulsi-adopt; anything else (and
  # `npm install` in a project) runs the real tool when there is one on PATH. Low
  # priority: installing the real tool system-wide replaces the shim.
  languageShims = map (
    tool:
    lib.lowPrio (
      pkgs.writeShellScriptBin tool ''
        install=
        if [ ${tool} = npm ]; then
          sub= global=
          for a in "$@"; do
            case "$a" in
              -g | --global) global=1 ;;
              -*) ;;
              *) [ -n "$sub" ] || sub=$a ;;
            esac
          done
          case "$sub" in install | i | add) [ -z "$global" ] || install=1 ;; esac
        else
          for a in "$@"; do
            case "$a" in
              -*) ;;
              *)
                [ "$a" != install ] || install=1
                break
                ;;
            esac
          done
        fi
        if [ -z "$install" ]; then
          self=$(${pkgs.coreutils}/bin/readlink -f "$0")
          IFS=:
          for dir in $PATH; do
            real="$dir/${tool}"
            if [ -x "$real" ] && [ "$(${pkgs.coreutils}/bin/readlink -f "$real")" != "$self" ]; then
              unset IFS
              exec "$real" "$@"
            fi
          done
          unset IFS
        fi
        exec ${adopt} shim ${tool} "$@"
      ''
    )
  ) cfg.languageCommands;

  desktopItem = pkgs.makeDesktopItem {
    name = "tulsi-adopt";
    desktopName = "Install the TulsiOS Way";
    comment = "Install downloaded software through the Software Center or the Assistant";
    exec = "${adopt} --file %f";
    icon = "system-software-install";
    noDisplay = true;
    mimeTypes = cfg.mimeTypes;
  };

  message = ''
    NixOS and TulsiOS cannot run programs built for other Linux distributions directly.
    TulsiOS can package it for you: see the "Install the TulsiOS Way" window, or ask
    the Assistant. (https://nix.dev/permalink/stub-ld)
  '';

  # Like nixpkgs' stub-ld (nixos/modules/config/stub-ld.nix), plus opening tulsi-adopt
  # with the program's path in a graphical session.
  stub = pkgs.pkgsStatic.runCommandCC "tulsi-stub-ld" {
    nativeBuildInputs = [ pkgs.unixtools.xxd ];
    inherit message;
  } ''
    printf "%s" "$message" | xxd -i -n message > main.c
    cat >> main.c <<'EOF'
    #include <fcntl.h>
    #include <stdio.h>
    #include <stdlib.h>
    #include <unistd.h>
    #include <sys/auxv.h>
    int main(int argc, char *argv[]) {
      const char *exe = (const char *)getauxval(AT_EXECFN);
      if (!exe) exe = argc > 0 ? argv[0] : "?";
      fprintf(stderr, "Could not start dynamically linked executable: %s\n", exe);
      fwrite(message, sizeof(unsigned char), message_len, stderr);
      if (getenv("DISPLAY") || getenv("WAYLAND_DISPLAY")) {
        pid_t pid = fork();
        if (pid == 0) {
          setsid();
          /* Don't hold the caller's pipes open: `$(./program)` must not wait for the window. */
          int null = open("/dev/null", O_RDWR);
          if (null >= 0) {
            dup2(null, 0); dup2(null, 1); dup2(null, 2);
            if (null > 2) close(null);
          }
          execl(ADOPT, ADOPT, "--binary", exe, (char *)NULL);
          _exit(127);
        }
      }
      return 127; /* like bash and zsh without a loader */
    }
    EOF
    $CC -Os -DADOPT='"${adopt}"' main.c -o $out
  '';
in
{
  options.tulsi.adopt = {
    enable = lib.mkEnableOption "the TulsiOS way for imperative install attempts";

    commands = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [
        "apt"
        "apt-get"
        "dnf"
        "yum"
        "pacman"
        "zypper"
        "snap"
        "brew"
      ];
      description = "Other systems' package commands that explain the TulsiOS way.";
    };

    languageCommands = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [
        "pip"
        "pip3"
        "pipx"
        "npm"
        "cargo"
        "gem"
        "go"
        "flatpak"
      ];
      description = ''
        Language and app installers whose install commands (`pip install`,
        `npm install -g`, `cargo install`, `flatpak install`, …) open the TulsiOS
        way. Other commands run the real tool when one is on PATH; installing the
        real tool system-wide replaces the shim.
      '';
    };

    mimeTypes = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [
        "application/vnd.debian.binary-package"
        "application/x-deb"
        "application/x-rpm"
        "application/x-redhat-package-manager"
        "application/vnd.appimage"
        "application/x-iso9660-appimage"
        "application/x-compressed-tar"
        "application/x-xz-compressed-tar"
        "application/x-bzip2-compressed-tar"
        "application/x-zstd-compressed-tar"
        "application/zip"
        "application/x-shellscript"
        "application/vnd.flatpak.ref"
        # Windows programs: the window offers Bottles (ADR 0034).
        "application/x-ms-dos-executable"
        "application/x-msdownload"
        "application/x-msi"
        "application/x-ms-installer"
      ];
      description = "Downloaded file types opened with tulsi-adopt by default.";
    };

    foreignBinaries = lib.mkOption {
      type = lib.types.bool;
      default = true;
      description = ''
        Replace NixOS's ELF-loader stub so that starting a program built for another
        distribution opens tulsi-adopt. Off when nix-ld or another loader is used.
      '';
    };
  };

  config = lib.mkIf cfg.enable {
    assertions = [
      {
        assertion = config.ocimum.softwareCenter.enable;
        message = "tulsi.adopt needs ocimum.softwareCenter (it provides tulsi-adopt).";
      }
    ];
    environment.systemPackages = shims ++ languageShims ++ [ desktopItem ];
    xdg.mime.enable = true;
    xdg.mime.defaultApplications = lib.genAttrs cfg.mimeTypes (_: "tulsi-adopt.desktop");
    environment.ldso = lib.mkIf (cfg.foreignBinaries && pkgs.stdenv.hostPlatform.isx86_64) stub;
  };
}
