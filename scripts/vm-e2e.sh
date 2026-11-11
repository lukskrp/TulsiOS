#!/usr/bin/env bash
# Real end-to-end test: boots the dev VM headless, then over SSH installs a
# package with `tulsi` (a real `nixos-rebuild` inside the VM, needs internet),
# checks it works, undoes it and checks it is gone.
#
# usage: scripts/vm-e2e.sh [PACKAGE]   (default: cowsay)
set -euo pipefail

PKG="${1:-cowsay}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PORT=2222
WORK="$(mktemp -d /tmp/tulsi-e2e.XXXX)"
VM_PID=""

cleanup() {
  [ -n "$VM_PID" ] && kill "$VM_PID" 2>/dev/null || true
  wait 2>/dev/null || true
  rm -rf "$WORK"
}
trap cleanup EXIT

log() { printf '\n==> %s\n' "$*"; }

log "building dev VM"
VM="$(nix build --no-link --print-out-paths "$REPO#nixosConfigurations.tulsi-vm.config.system.build.vm")"
TOOLS="$(nix build --no-link --print-out-paths --inputs-from "$REPO" nixpkgs#sshpass nixpkgs#openssh | tr '\n' ':')"
export PATH="${TOOLS//:/\/bin:}$PATH"

log "booting VM headless (disk in $WORK)"
(
  cd "$WORK"
  NIX_DISK_IMAGE="$WORK/tulsi-vm.qcow2" \
  QEMU_NET_OPTS="hostfwd=tcp:127.0.0.1:$PORT-:22" \
  QEMU_OPTS="-display none" \
    "$VM/bin/run-tulsi-vm-vm" >"$WORK/console.log" 2>&1
) &
VM_PID=$!

vm() {
  sshpass -p tulsi ssh -F /dev/null -p "$PORT" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    -o LogLevel=ERROR -o ConnectTimeout=5 tulsi@127.0.0.1 "$@"
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

log "PASS: install -> available -> undo -> gone"
