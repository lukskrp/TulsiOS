# A package file
id: package-file
keys: callPackage, package.nix
see: function-arguments, mkderivation, tulsios-local-package

A package file is a function from what it needs to a **derivation**, a description of how to build. TulsiOS calls it with the system's packages, matched by argument name:

- `stdenv`: the compiler and standard build steps, with `stdenv.mkDerivation` ([[mkderivation]]);
- `lib`: helper functions ([[lib]]);
- fetchers, or `requireFile` for a downloaded file ([[tulsios-download]]);
- any package by its name: `zlib`, `gtk3`, `openssl`, `python3`.

**Not sure of a name?** In the arguments, type the start of it and press **Ctrl+Space**, or write `pkgs.` in the body to browse; hovering over a package shows what it is.

```nix
{ lib, stdenv, requireFile, zlib }:

stdenv.mkDerivation {
  pname = "frob";
  version = "1.0";
  src = requireFile {
    name = "frob-1.0-frob.tar.gz";
    hash = "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=";
    message = "Added to the Nix store by TulsiOS.";
  };
  buildInputs = [ zlib ];
  meta.license = lib.licenses.mit;
}
```

# stdenv.mkDerivation
id: mkderivation
keys: mkDerivation, stdenv.mkDerivation, stdenv
see: pname-version, src, inputs, phases, meta

`stdenv.mkDerivation { … }` builds software with the standard steps: unpack `src`, then configure, build, install ([[phases]]). It knows autotools, plain Makefiles, and with the right hooks in `nativeBuildInputs` also CMake, Meson and others ([[build-systems]]).

The names you give it:

- `pname`, `version` ([[pname-version]])
- `src`: what to build from ([[src]])
- `nativeBuildInputs`, `buildInputs` ([[inputs]])
- phases and their options, such as `installPhase` or `dontBuild = true;` ([[phases]])
- `meta`: description, licence, main program ([[meta]])

Whatever the install step puts in `$out` is the package ([[out]]).

```nix
{ lib, stdenv, requireFile }:
stdenv.mkDerivation {
  pname = "frob";
  version = "1.0";
  src = requireFile {
    name = "frob-1.0-frob.tar.gz";
    hash = "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=";
    message = "Added to the Nix store by TulsiOS.";
  };
  meta.license = lib.licenses.mit;
}
```

Typing `mkDerivation` offers this skeleton:

```nix snippet
stdenv.mkDerivation {
  pname = "name";
  version = "1.0";
  src = src;
  nativeBuildInputs = [ ];
  buildInputs = [ ];
  meta = {
    description = "What it does";
    license = lib.licenses.mit;
    mainProgram = "name";
  };
}
```

# pname and version
id: pname-version
keys: pname, version, name
see: mkderivation, tulsios-local-package

`pname` is the package's name and `version` its version; together they name the build `pname-version`. In a TulsiOS local package, `pname` should be the name you install it as: lower-case letters, digits and dashes.

```nix
{ pname = "frob"; version = "1.2.0"; }
```

# src
id: src
keys: src
see: tulsios-download, fetchers, hashes, phases

`src` is what the package is built from: an archive, a single file or a source tree. In TulsiOS, a package made from a download uses `requireFile` with the file's hash ([[tulsios-download]]); sources on the internet use a fetcher ([[fetchers]]).

When `src` is a single program rather than an archive, set `dontUnpack = true;` and copy `$src` in the install step.

```nix
{ requireFile }:
{
  src = requireFile {
    name = "frob-1.0-frob";
    hash = "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=";
    message = "Added to the Nix store by TulsiOS.";
  };
  dontUnpack = true;
}
```

# Fetchers: fetchurl, fetchzip, fetchFromGitHub
id: fetchers
keys: fetchurl, fetchzip, fetchFromGitHub, fetchFromGitLab, fetchgit, fetchpatch
see: hashes, src, lib-fakehash

Fetchers download a source during the build and check it against its `hash`, so the build is the same everywhere.

- `fetchurl { url; hash; }`: one file
- `fetchzip { url; hash; }`: an archive, unpacked (the hash covers the unpacked files)
- `fetchFromGitHub { owner; repo; rev; hash; }`: a GitHub repository at a tag or commit

Do not know the hash yet? Use `lib.fakeHash`, build, and copy the hash after `got:` ([[hashes]]).

```nix
{ lib, fetchFromGitHub }:
fetchFromGitHub {
  owner = "example";
  repo = "frob";
  rev = "v1.0";
  hash = lib.fakeHash;
}
```

# Hashes
id: hashes
keys: hash, sha256, outputHash
see: fetchers, lib-fakehash, tulsios-build-log

Every download in a package has a hash, like `sha256-…=`. If the file changes, the build stops instead of using something else.

**Finding a hash:** put `lib.fakeHash` (or `""`) in its place and build. The log then says

```text
specified: sha256-AAAA…
     got:    sha256-Xyz…
```

and the `got:` hash is the right one. Rust and Go packages also have a hash for their dependencies, `cargoHash` and `vendorHash`, found the same way.

```nix
{ lib }:
{ hash = lib.fakeHash; }
```

# nativeBuildInputs and buildInputs
id: inputs
keys: buildInputs, nativeBuildInputs, propagatedBuildInputs, runtimeDependencies
see: mkderivation, build-systems, autopatchelf, tulsios-build-log

Two lists of packages the build needs:

- `nativeBuildInputs`: **tools that run during the build**, such as `pkg-config`, `cmake`, `meson`, `ninja`, `autoPatchelfHook` and `makeWrapper`;
- `buildInputs`: **libraries the program uses**, such as `zlib`, `openssl` and `gtk3`.

Each must also be an argument of the file: `{ stdenv, pkg-config, zlib }:`. When a build says `Package 'gtk+-3.0' … not found` or `Could NOT find ZLIB`, a library is missing from `buildInputs` ([[tulsios-build-log]]).

```nix
{ stdenv, pkg-config, zlib, openssl }:
stdenv.mkDerivation {
  pname = "frob";
  version = "1.0";
  nativeBuildInputs = [ pkg-config ];
  buildInputs = [ zlib openssl ];
}
```

# Phases: unpack, configure, build, install
id: phases
keys: installPhase, buildPhase, unpackPhase, configurePhase, checkPhase, fixupPhase, patchPhase, dontUnpack, dontBuild, dontConfigure, doCheck, sourceRoot, preInstall, postInstall, preBuild, postBuild, postUnpack, patches
see: runhook, out, indented-strings

`mkDerivation` builds in steps, called **phases**. Each has a sensible default; change one by writing its shell commands as an [[indented-strings|indented string]].

- `unpackPhase`: unpacks `src`. Use `dontUnpack = true;` for a single file, and `sourceRoot = "folder";` when the archive's folder name is unusual.
- `configurePhase`: runs `./configure`, or CMake or Meson. Use `dontConfigure = true;` to skip it.
- `buildPhase`: runs `make`. Use `dontBuild = true;` to skip it.
- `installPhase`: copies the results into `$out` ([[out]]).

`postInstall = '' … '';` adds commands after the default install instead of replacing it.

```nix
{ stdenv }:
stdenv.mkDerivation {
  pname = "frob";
  version = "1.0";
  dontBuild = true;
  installPhase = ''
    runHook preInstall
    install -Dm755 frob $out/bin/frob
    runHook postInstall
  '';
}
```

# runHook
id: runhook
keys: runHook
see: phases

A phase you write yourself should start with `runHook preInstall` and end with `runHook postInstall`, or `preBuild`/`postBuild` and so on. Hooks such as `autoPatchelfHook` and `makeWrapper`, and `postInstall` lines, then still run.

```nix
''
  runHook preInstall
  cp -r . $out
  runHook postInstall
''
```

# $out
id: out
keys: out, "$out"
see: phases, wrappers

`$out` is the package's folder in the Nix store. Programs go in `$out/bin`, libraries in `$out/lib`, menu entries in `$out/share/applications` and icons in `$out/share/icons`. TulsiOS puts programs from `$out/bin` on everyone's PATH.

- `install -Dm755 file $out/bin/name` copies a program, making the folders on the way.
- `cp -a folder/. $out/` copies everything.

```nix
''
  mkdir -p $out/bin $out/share/applications
  install -Dm755 frob $out/bin/frob
''
```

# CMake, Meson, autotools, make
id: build-systems
keys: cmake, meson, ninja, pkg-config, autoreconfHook, cmakeFlags, mesonFlags, makeFlags, configureFlags
see: inputs, phases

`mkDerivation` builds with `./configure && make && make install` by default. For other build systems, add their tools to `nativeBuildInputs`, and the phases use them:

- **CMake:** `nativeBuildInputs = [ cmake ];`, with options in `cmakeFlags = [ "-DFOO=ON" ];`
- **Meson:** `nativeBuildInputs = [ meson ninja pkg-config ];`, with options in `mesonFlags`
- **autotools without a configure script:** add `autoreconfHook`
- **a plain Makefile:** set `makeFlags = [ "PREFIX=$(out)" ];`

```nix
{ stdenv, cmake, pkg-config, zlib }:
stdenv.mkDerivation {
  pname = "frob";
  version = "1.0";
  nativeBuildInputs = [ cmake pkg-config ];
  buildInputs = [ zlib ];
  cmakeFlags = [ "-DBUILD_TESTS=OFF" ];
}
```

# autoPatchelfHook: prebuilt programs
id: autopatchelf
keys: autoPatchelfHook, autoPatchelfIgnoreMissingDeps, appendRunpaths
see: inputs, tulsios-build-log, wrappers

Programs built for other Linux systems look for their libraries in `/usr/lib`, which TulsiOS does not have. `autoPatchelfHook` in `nativeBuildInputs` points them at the libraries in `buildInputs` instead.

If the build says `could not satisfy dependency libX.so.6`, add the package that has that library to `buildInputs` (completion and hover help find it). `autoPatchelfIgnoreMissingDeps = [ "libX.so.6" ];` builds without it, and the program may then miss a feature.

`runtimeDependencies = [ … ];` adds libraries that a program opens by itself while running, such as `libGL` or `libpulseaudio`.

```nix
{ stdenv, autoPatchelfHook, zlib, libGL }:
stdenv.mkDerivation {
  pname = "frob";
  version = "1.0";
  nativeBuildInputs = [ autoPatchelfHook ];
  buildInputs = [ zlib stdenv.cc.cc.lib ];
  runtimeDependencies = [ libGL ];
}
```

# makeWrapper
id: wrappers
keys: makeWrapper, wrapProgram, makeBinaryWrapper, wrapGAppsHook3, wrapQtAppsHook
see: lib-makelibrarypath, out

A wrapper is a tiny program that sets things up, then starts the real one. Add `makeWrapper` to `nativeBuildInputs`, then in `postInstall`:

- `wrapProgram $out/bin/frob --prefix PATH : ${lib.makeBinPath [ git ]}` gives it other programs;
- `--prefix LD_LIBRARY_PATH : ${lib.makeLibraryPath [ libGL ]}` gives it libraries it loads by itself;
- `--set NAME value` sets an environment variable;
- `--add-flags "--no-update"` adds arguments.

GTK applications get `wrapGAppsHook3` instead, and Qt applications `qt6.wrapQtAppsHook`.

```nix
{ lib, stdenv, makeWrapper, git }:
stdenv.mkDerivation {
  pname = "frob";
  version = "1.0";
  nativeBuildInputs = [ makeWrapper ];
  postInstall = ''
    wrapProgram $out/bin/frob --prefix PATH : ${lib.makeBinPath [ git ]}
  '';
}
```

# meta
id: meta
keys: meta, description, homepage, mainProgram, platforms, lib.platforms, longDescription
see: lib-licenses, lib-getexe

`meta` describes the package to people and tools:

- `description`: one short line, shown in the Software Center;
- `homepage`;
- `license` ([[lib-licenses]]);
- `mainProgram`: the program that `lib.getExe` and the Software Center start;
- `platforms`: where it runs, such as `lib.platforms.linux`.

```nix
{ lib }:
{
  meta = {
    description = "Frobnicates files";
    homepage = "https://example.org/frob";
    license = lib.licenses.mit;
    mainProgram = "frob";
    platforms = lib.platforms.linux;
  };
}
```

# Rust programs: rustPlatform.buildRustPackage
id: rust
keys: rustPlatform, buildRustPackage, rustPlatform.buildRustPackage, cargoHash, cargoLock
see: hashes, inputs

Rust programs (with a `Cargo.toml`) build with `rustPlatform.buildRustPackage`. It downloads the dependencies listed in `Cargo.lock`, checked by `cargoHash`: start with `lib.fakeHash` and copy the hash after `got:` ([[hashes]]).

Libraries the crates link to, such as `openssl`, go in `buildInputs`, with `pkg-config` in `nativeBuildInputs`.

```nix
{ lib, rustPlatform, requireFile, pkg-config, openssl }:
rustPlatform.buildRustPackage {
  pname = "frob";
  version = "1.0";
  src = requireFile {
    name = "frob-1.0-frob.tar.gz";
    hash = "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=";
    message = "Added to the Nix store by TulsiOS.";
  };
  cargoHash = lib.fakeHash;
  nativeBuildInputs = [ pkg-config ];
  buildInputs = [ openssl ];
}
```

# Go programs: buildGoModule
id: go
keys: buildGoModule, vendorHash, subPackages, ldflags
see: hashes

Go programs (with a `go.mod`) build with `buildGoModule`. `vendorHash` checks the downloaded modules: start with `lib.fakeHash` and copy the `got:` hash. Use `vendorHash = null;` when the source already has a `vendor` folder.

`subPackages = [ "cmd/frob" ];` builds only some of the programs.

```nix
{ lib, buildGoModule, requireFile }:
buildGoModule {
  pname = "frob";
  version = "1.0";
  src = requireFile {
    name = "frob-1.0-frob.tar.gz";
    hash = "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=";
    message = "Added to the Nix store by TulsiOS.";
  };
  vendorHash = lib.fakeHash;
  subPackages = [ "cmd/frob" ];
}
```

# AppImages: appimageTools.wrapType2
id: appimage
keys: appimageTools, wrapType2, appimageTools.wrapType2, appimageTools.extract, extraInstallCommands, extraPkgs
see: src, meta

An AppImage carries its own libraries; `appimageTools.wrapType2` runs it in a small environment that looks like an ordinary Linux system. `appimageTools.extract` unpacks it, so `extraInstallCommands` can copy its menu entry and icon. `extraPkgs = pkgs: [ … ];` adds libraries the AppImage expects from the system.

```nix
{ lib, appimageTools, requireFile }:
let
  pname = "frob";
  version = "1.0";
  src = requireFile {
    name = "frob-1.0-Frob.AppImage";
    hash = "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=";
    message = "Added to the Nix store by TulsiOS.";
  };
in
appimageTools.wrapType2 {
  inherit pname version src;
  meta.license = lib.licenses.unfree;
}
```

# Menu entries: makeDesktopItem
id: desktop-items
keys: makeDesktopItem, copyDesktopItems, desktopItems
see: out, meta

A program appears in the applications menu through a `.desktop` file in `$out/share/applications`. `makeDesktopItem` writes one; add `copyDesktopItems` to `nativeBuildInputs` and list the items in `desktopItems`.

```nix
{ stdenv, makeDesktopItem, copyDesktopItems }:
stdenv.mkDerivation {
  pname = "frob";
  version = "1.0";
  nativeBuildInputs = [ copyDesktopItems ];
  desktopItems = [
    (makeDesktopItem {
      name = "frob";
      exec = "frob";
      icon = "frob";
      desktopName = "Frob";
      categories = [ "Utility" ];
    })
  ];
}
```

# pkgs
id: pkgs
keys: pkgs
see: package-file, function-arguments

`pkgs` is the whole package collection. In a package file it is better to ask for each package by name (`{ zlib, openssl }:`), but `pkgs.` followed by **Ctrl+Space** is a handy way to browse names, and hovering over `pkgs.name` says what that package is.

```nix
{ pkgs }:
[ pkgs.hello pkgs.zlib ]
```
