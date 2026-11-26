# USB sticks

Write TulsiOS (or any ISO) to a stick, and make sticks for carrying files
(app menu → USB Stick Writer, or `tulsi-stick`).

- **Only USB drives are listed** — the system disk can never be picked by
  accident. Unmount a drive first if it is mounted.
- **Write Image:** pick the ISO, pick the drive, type the drive name to
  confirm. The stick is read back and checked, so a bad write tells you
  instead of failing to boot.
- **Format:** wipe the drive and make one fresh partition — FAT32 for
  everywhere, exFAT for big files everywhere, NTFS for Windows, ext4 for
  Linux — with a short name.
- Backing up to the same stick first is one window away (Backup).
