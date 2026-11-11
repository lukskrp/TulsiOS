# Development setup (Windows 11 + WSL2)

The repository must live on a Linux filesystem (ext4). NTFS and exFAT break
symlinks, file modes and case sensitivity, and they are slow through WSL.

## 1. Put the WSL distro on the big drive
```powershell
wsl --shutdown
wsl --manage Ubuntu --move D:\WSL\Ubuntu     # needs WSL >= 2.3
wsl --manage Ubuntu --set-sparse true        # optional: give freed space back to Windows
```
The distro's `D:\WSL\Ubuntu\ext4.vhdx` is the ext4 disk; the repo lives at `~/TulsiOS`.

## 2. `%UserProfile%\.wslconfig`
```ini
[wsl2]
memory=40GB
nestedVirtualization=true
```

## 3. systemd in Ubuntu: `/etc/wsl.conf`
```ini
[boot]
systemd=true
```
Then `wsl --shutdown` from Windows.

## 4. Nix (multi-user) with flakes
```sh
sh <(curl -L https://nixos.org/nix/install) --daemon
# /etc/nix/nix.conf
experimental-features = nix-command flakes
trusted-users = root <your-user>
max-jobs = auto
```

## 5. KVM (dev VM and NixOS tests)
```sh
ls -l /dev/kvm
sudo usermod -aG kvm $USER
```

## 6. Editing from Windows
Use VS Code with the "WSL" extension (`code ~/TulsiOS` inside WSL), or open
`\\wsl$\Ubuntu\home\<user>\TulsiOS` in Explorer.

## Daily commands
```sh
cd ~/TulsiOS
nix develop
cargo test
nix flake check
nix build .#nixosConfigurations.tulsi-vm.config.system.build.vm && ./result/bin/run-tulsi-vm-vm
nix fmt
```
The VM window is displayed through WSLg.
