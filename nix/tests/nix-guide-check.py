"""Every example in the Nix Editor's guide parses, and the packaging and TulsiOS
examples that are package files pass TulsiOS's rules for local packages (ADR 0019).

usage: nix-guide-check.py APP_DIR TULSI
"""

import os
import subprocess
import sys
import tempfile

sys.path.insert(0, sys.argv[1])
from ocimum_nix_editor.guide import Guide  # noqa: E402

tulsi = sys.argv[2]
guide = Guide.load()
failures = []
work = tempfile.mkdtemp()
checked = 0
for e in guide.entries:
    for name, code in (("example", e.example), ("snippet", e.snippet)):
        if not code:
            continue
        path = os.path.join(work, f"{e.id}-{name}.nix")
        with open(path, "w", encoding="utf-8") as f:
            # A snippet goes into a package's body: parse it with the names it uses.
            f.write(("{ lib, stdenv, src }:\n" if name == "snippet" else "") + code + "\n")
        parse = subprocess.run(["nix-instantiate", "--parse", path], capture_output=True, text=True)
        if parse.returncode != 0:
            failures.append(f"{e.id} ({name}) does not parse:\n{parse.stderr}")
        checked += 1
        if name == "example" and e.topic in ("packaging", "tulsios") and code.lstrip().startswith("{"):
            check = subprocess.run([tulsi, "recipe", "check", path], capture_output=True, text=True)
            if check.returncode != 0:
                failures.append(f"{e.id}: TulsiOS refuses its example: {check.stdout}")
if guide.broken_links():
    failures.append("broken links: " + ", ".join(guide.broken_links()))
print(f"checked {checked} examples in {len(guide.entries)} entries")
if failures:
    print("\n\n".join(failures))
    sys.exit(1)
