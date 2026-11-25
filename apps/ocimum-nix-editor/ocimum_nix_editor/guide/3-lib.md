# lib
id: lib
keys: lib
see: lib-optional, lib-licenses, lib-getexe, lib-makelibrarypath, builtins

`lib` is nixpkgs' library of helper functions. A package asks for it like any other argument: `{ lib, stdenv }:`. Type `lib.` and press **Ctrl+Space** to see them all.

The ones packages use most:

- `lib.optional`, `lib.optionals`, `lib.optionalString` ([[lib-optional]])
- `lib.licenses` ([[lib-licenses]])
- `lib.getExe`, `lib.getBin` ([[lib-getexe]])
- `lib.makeLibraryPath`, `lib.makeBinPath` ([[lib-makelibrarypath]])
- `lib.platforms` ([[meta]])

```nix
{ lib }:
lib.concatStringsSep ", " [ "a" "b" ]
```

# lib.optional, lib.optionals, lib.optionalString
id: lib-optional
keys: lib.optional, lib.optionals, lib.optionalString, lib.optionalAttrs, optional, optionals, optionalString, optionalAttrs
see: if, lists

Add something only when a condition holds:

- `lib.optional cond x`: `[ x ]` or `[ ]`
- `lib.optionals cond [ x y ]`: the list, or `[ ]`
- `lib.optionalString cond "text"`: the text, or `""`
- `lib.optionalAttrs cond { … }`: the set, or `{ }`

```nix
{ lib, stdenv, zlib, wayland }:
[ zlib ] ++ lib.optional stdenv.hostPlatform.isLinux wayland
```

# lib.licenses
id: lib-licenses
keys: lib.licenses, licenses, license
see: meta, tulsios-unfree

`meta.license` says under which terms the software may be used: `lib.licenses.mit`, `lib.licenses.gpl3Plus`, `lib.licenses.asl20`, `lib.licenses.bsd3`. Software you may use but not share is `lib.licenses.unfree`. Type `lib.licenses.` and press **Ctrl+Space** for the full list.

TulsiOS installs proprietary (unfree) software only after you accept its licence ([[tulsios-unfree]]).

```nix
{ lib }:
{ license = lib.licenses.unfree; }
```

# lib.getExe
id: lib-getexe
keys: lib.getExe, lib.getExe', lib.getBin, lib.getLib, lib.getDev, getExe, getBin
see: meta, wrappers

`lib.getExe pkg` is the path of a package's main program (from its `meta.mainProgram`). `lib.getExe' pkg "name"` picks another program. `lib.getBin pkg` is the part of the package with `bin/`.

```nix
{ lib, hello }:
"${lib.getExe hello} --version"
```

# lib.makeLibraryPath, lib.makeBinPath
id: lib-makelibrarypath
keys: lib.makeLibraryPath, lib.makeBinPath, makeLibraryPath, makeBinPath
see: wrappers, autopatchelf

`lib.makeLibraryPath [ a b ]` gives `a/lib:b/lib`, for `LD_LIBRARY_PATH`. `lib.makeBinPath [ a b ]` gives `a/bin:b/bin`, for `PATH`. Both are used with [[wrappers|makeWrapper]] for programs that load libraries or run other programs at run time.

```nix
{ lib, zlib, libGL }:
lib.makeLibraryPath [ zlib libGL ]
```

# lib.fakeHash
id: lib-fakehash
keys: lib.fakeHash, fakeHash, lib.fakeSha256
see: hashes, fetchers

`lib.fakeHash` stands in for a hash you do not know yet. The build then fails and prints the right one after `got:`; copy it in ([[hashes]]).

```nix
{ lib }:
{ hash = lib.fakeHash; }
```

# Strings in lib
id: lib-strings
keys: lib.concatStringsSep, lib.concatMapStringsSep, lib.versions, lib.toLower, lib.hasPrefix, lib.hasSuffix, lib.removePrefix, lib.replaceStrings, concatStringsSep
see: strings

Helpers for strings:

- `lib.concatStringsSep ", " list` joins a list of strings.
- `lib.hasPrefix "lib" name` and `lib.hasSuffix ".so" name` test for a beginning or ending.
- `lib.removePrefix "v" "v1.2"` gives `"1.2"`.
- `lib.versions.majorMinor "1.2.3"` gives `"1.2"`.

```nix
{ lib }:
lib.removePrefix "v" "v1.2"
```
