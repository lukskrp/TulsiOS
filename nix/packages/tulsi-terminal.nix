# tulsi-terminal [--hold] [--] COMMAND [ARGS…]: runs a command in the desktop's own
# terminal (GNOME Terminal on Ocimum, Konsole on SonicDE, st on dwm), so a
# launcher or an app can open a terminal tool without knowing the desktop.
# --hold waits for Enter before the window closes, to leave the output to read.
{ writeShellApplication }:

writeShellApplication {
  name = "tulsi-terminal";
  text = ''
    hold=
    while [ $# -gt 0 ]; do
      case "$1" in
        --hold) hold=1; shift ;;
        --) shift; break ;;
        *) break ;;
      esac
    done
    if [ $# -eq 0 ]; then
      echo "usage: tulsi-terminal [--hold] [--] COMMAND [ARGS...]" >&2
      exit 2
    fi
    if [ -n "$hold" ]; then
      # shellcheck disable=SC2016
      set -- sh -c '"$@"; status=$?; printf "\nPress Enter to close this window. "; read -r _; exit $status' tulsi-terminal "$@"
    fi

    case "''${XDG_CURRENT_DESKTOP:-}" in
      *[Cc]innamon*) order="gnome-terminal konsole st xterm" ;;
      *KDE* | *[Ss]onic*) order="konsole gnome-terminal st xterm" ;;
      *) order="st gnome-terminal konsole xterm" ;;
    esac
    for terminal in $order; do
      command -v "$terminal" >/dev/null || continue
      case "$terminal" in
        gnome-terminal) exec gnome-terminal --wait -- "$@" ;;
        konsole) exec konsole -e "$@" ;;
        *) exec "$terminal" -e "$@" ;;
      esac
    done
    echo "tulsi-terminal: no terminal found (tried: $order)" >&2
    exit 1
  '';
}
