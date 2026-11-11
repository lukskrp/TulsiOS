#!/usr/bin/env bash
# Real end-to-end test of the dev VM (Cinnamon, GTK3-O grafted), headless:
#   1. `tulsi install PKG` over SSH: a real `nixos-rebuild` inside the VM
#      (needs internet), check it works, `tulsi undo`, check it is gone.
#   2. Desktop: check Cinnamon's GTK processes load GTK3-O, open the Software
#      Center in the Cinnamon session and take screenshots.
#
# usage: scripts/vm-e2e.sh [PACKAGE]   (default: cowsay)
# Screenshots go to $E2E_OUT (default: ./e2e-out).
set -euo pipefail

PKG="${1:-cowsay}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${E2E_OUT:-$PWD/e2e-out}"
PORT=2222
WORK="$(mktemp -d /tmp/tulsi-e2e.XXXX)"
VM_PID=""
mkdir -p "$OUT"

cleanup() {
  [ -n "$VM_PID" ] && kill "$VM_PID" 2>/dev/null || true
  wait 2>/dev/null || true
  rm -rf "$WORK"
}
trap cleanup EXIT

log() { printf '\n==> %s\n' "$*"; }

log "building dev VM"
VM="$(nix build --no-link --print-out-paths "$REPO#nixosConfigurations.tulsi-vm.config.system.build.vm")"
GTK3O="$(nix eval --raw "$REPO#nixosConfigurations.tulsi-vm.config.ocimum.gtk3o.package.outPath")"
TOOLS="$(nix build --no-link --print-out-paths --inputs-from "$REPO" \
  nixpkgs#sshpass nixpkgs#openssh nixpkgs#socat nixpkgs#imagemagick | tr '\n' ':')"
export PATH="${TOOLS//:/\/bin:}$PATH"

log "booting VM headless (disk in $WORK)"
(
  cd "$WORK"
  NIX_DISK_IMAGE="$WORK/tulsi-vm.qcow2" \
  QEMU_NET_OPTS="hostfwd=tcp:127.0.0.1:$PORT-:22" \
  QEMU_OPTS="-display none -monitor unix:$WORK/monitor,server,nowait" \
    "$VM/bin/run-tulsi-vm-vm" >"$WORK/console.log" 2>&1
) &
VM_PID=$!

vm() {
  sshpass -p tulsi ssh -F /dev/null -p "$PORT" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    -o LogLevel=ERROR -o ConnectTimeout=5 tulsi@127.0.0.1 "$@"
}

# Run a command inside tulsi's graphical (Cinnamon) session.
SESSION_ENV='DISPLAY=:0 XDG_RUNTIME_DIR=/run/user/$(id -u) DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u)/bus'
in_session() { vm "export $SESSION_ENV; $*"; }

screenshot() {
  echo "screendump $WORK/shot.ppm" | socat - "UNIX-CONNECT:$WORK/monitor" >/dev/null
  sleep 1
  magick "$WORK/shot.ppm" "$OUT/$1.png"
  echo "screenshot: $OUT/$1.png"
}

gtk_libs() { # PID -> distinct libgtk-3 store paths it has mapped
  vm "grep -o '/nix/store/[^ ]*/libgtk-3.so[^ ]*' /proc/$1/maps | sed 's|/lib/libgtk-3.*||' | sort -u"
}

log "waiting for SSH and tulsid"
for i in $(seq 1 120); do
  if vm 'systemctl is-active --quiet tulsid && test -e /etc/nixos/flake.nix' 2>/dev/null; then break; fi
  if ! kill -0 "$VM_PID" 2>/dev/null; then echo "VM exited"; tail -50 "$WORK/console.log"; exit 1; fi
  [ "$i" -eq 120 ] && { echo "timed out"; tail -50 "$WORK/console.log"; exit 1; }
  sleep 5
done

log "generated system flake"
vm 'ls /etc/nixos /etc/nixos/tulsi && tulsi history'

log "tulsi install $PKG (real nixos-rebuild inside the VM)"
vm "tulsi install $PKG"
vm "command -v $PKG"

log "tulsi undo"
vm "tulsi undo"
if vm "command -v $PKG" >/dev/null 2>&1; then echo "FAIL: $PKG still installed after undo"; exit 1; fi

log "history"
vm 'tulsi history'

CINNAMON_RE='bin/\.?cinnamon(-wrapped)?( |$)'
log "desktop: waiting for the Cinnamon session"
for i in $(seq 1 60); do
  # nixpkgs wraps binaries, so match on the command line, not the name.
  vm "pgrep -u tulsi -f '$CINNAMON_RE' >/dev/null" && break
  if [ "$i" -eq 60 ]; then
    echo "Cinnamon did not start; processes of tulsi:"
    vm 'ps -u tulsi -o pid=,args= | cut -c1-150' || true
    screenshot 00-no-cinnamon
    exit 1
  fi
  sleep 5
done
sleep 10
screenshot 01-desktop

log "desktop: GTK3-O is what Cinnamon's GTK processes load"
for proc in "$CINNAMON_RE" 'nemo-desktop'; do
  pid="$(vm "pgrep -u tulsi -o -f '$proc'" || true)"
  [ -z "$pid" ] && { echo "  $proc: not running, skipped"; continue; }
  libs="$(gtk_libs "$pid")"
  echo "  $proc: $libs"
  [ "$libs" = "$GTK3O" ] || { echo "FAIL: $proc does not use GTK3-O ($GTK3O)"; exit 1; }
done

log "desktop: Software Center"
in_session 'nohup ocimum-software-center >/tmp/sc.log 2>&1 &'
for i in $(seq 1 30); do
  in_session "gdbus call --session --dest org.freedesktop.DBus --object-path /org/freedesktop/DBus \
    --method org.freedesktop.DBus.NameHasOwner org.tulsi.SoftwareCenter" | grep -q true && break
  [ "$i" -eq 30 ] && { echo "FAIL: Software Center did not start"; vm 'cat /tmp/sc.log'; exit 1; }
  sleep 2
done
sleep 3
in_session "gdbus call --session --dest org.tulsi.SoftwareCenter --object-path /org/tulsi/SoftwareCenter \
  --method org.gtk.Actions.Activate search \"[<'video player'>]\" '{}'" >/dev/null
sleep 4
screenshot 02-software-center-search
pid="$(vm 'pgrep -u tulsi -f ocimum-software-center | head -1')"
libs="$(gtk_libs "$pid")"
echo "  ocimum-software-center: $libs"
[ "$libs" = "$GTK3O" ] || { echo "FAIL: Software Center does not use GTK3-O"; exit 1; }
vm 'cat /tmp/sc.log' || true

log "browser: adoption of a store-installed Firefox extension"
in_session 'systemctl --user is-active tulsi-extwatch'
# Simulate what Firefox writes after installing Bitwarden from addons.mozilla.org.
EXT='{446900e4-71c2-419f-a6a7-df9c091e268b}'
vm "mkdir -p ~/.mozilla/firefox/e2e.default && cat > ~/.mozilla/firefox/e2e.default/extensions.json" <<EOF
{"schemaVersion": 36, "addons": [{"id": "$EXT", "type": "extension", "location": "app-profile",
  "sourceURI": "https://addons.mozilla.org/firefox/downloads/file/4440363/bitwarden_password_manager.xpi",
  "defaultLocale": {"name": "Bitwarden Password Manager"}}]}
EOF
sleep 3
screenshot 03-extension-notice
for i in $(seq 1 60); do
  vm "grep -qF '$EXT' /etc/nixos/tulsi/state.json" && break
  [ "$i" -eq 60 ] && { echo "FAIL: extension was not adopted"; in_session 'journalctl --user -u tulsi-extwatch --no-pager | tail -20'; exit 1; }
  sleep 5
done
# Adoption triggers a real rebuild; wait for it to finish and the policy to change.
for i in $(seq 1 60); do
  vm "grep -qF '$EXT' /etc/firefox/policies/policies.json" && break
  [ "$i" -eq 60 ] && { echo "FAIL: Firefox policy does not contain the extension"; exit 1; }
  sleep 5
done
echo "  state.json and Firefox policy contain $EXT"
vm 'tulsi history 3'
sleep 2
screenshot 04-extension-done

log "browser: Firefox installs the adopted extension from policy (best effort, needs network)"
if vm "rm -rf /tmp/ffp && mkdir /tmp/ffp && timeout 90 firefox --headless --profile /tmp/ffp about:blank >/dev/null 2>&1; \
       grep -qF '$EXT' /tmp/ffp/extensions.json"; then
  echo "  Firefox installed $EXT via policy"
else
  echo "  (skipped: Firefox did not finish installing from policy within 90 s)"
fi

log "PASS: install -> available -> undo -> gone; Cinnamon + Software Center on GTK3-O; extension adopted"
