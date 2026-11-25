# A TulsiOS local package
id: tulsios-local-package
keys:
see: package-file, tulsios-download, tulsios-refused, tulsios-build-and-install

Software TulsiOS has no package for is installed as a **local package**: one `package.nix` that becomes part of this computer's configuration, with the Software Center's confirmation, history and Undo.

A local package must:

- be a function of what it needs: `{ lib, stdenv, requireFile }: …` ([[package-file]]);
- get its files from hashed sources only: the downloaded file through `requireFile` ([[tulsios-download]]), or a fetcher;
- avoid what could read or change this computer while it is built ([[tulsios-refused]]).

When a Recipe could not finish, its draft opens here with the build log below. Fix what the log points at, then **Build and Try** and **Install** ([[tulsios-build-and-install]]).

```nix
{ lib, stdenv, requireFile, autoPatchelfHook, zlib }:

stdenv.mkDerivation {
  pname = "frob";
  version = "1.0";
  src = requireFile {
    name = "frob-1.0-frob";
    hash = "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=";
    message = "Added to the Nix store by TulsiOS (tulsi-adopt).";
  };
  dontUnpack = true;
  nativeBuildInputs = [ autoPatchelfHook ];
  buildInputs = [ zlib ];
  installPhase = ''
    runHook preInstall
    install -Dm755 $src $out/bin/frob
    runHook postInstall
  '';
  meta = {
    description = "Frobnicates files";
    license = lib.licenses.unfree;
    mainProgram = "frob";
  };
}
```

# The downloaded file: requireFile
id: tulsios-download
keys: requireFile, message
see: src, hashes, tulsios-kept

When you install a download, TulsiOS adds the file to the Nix store, and the package refers to it with `requireFile`, by its **name and hash**. Keep both exactly as the Recipe wrote them: they identify that one file. Nix then builds from it without reading anything else on the computer.

The file's store name starts with the package's name and version, so changing `pname` or `version` does not need a new `name` here.

```nix
{ requireFile }:
requireFile {
  name = "frob-1.0-frob.deb";
  hash = "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=";
  message = "Added to the Nix store by TulsiOS (tulsi-adopt).";
}
```

# What TulsiOS refuses in a package
id: tulsios-refused
keys: readFile, getEnv, builtins.readFile, builtins.getEnv, builtins.fetchurl, builtins.fetchGit, builtins.path, builtins.storePath, __noChroot, impureEnvVars
see: paths, import, tulsios-local-package

This computer's configuration is rebuilt as the administrator, so TulsiOS checks every local package before it is built. It refuses:

- **paths** such as `./file` or `/home/…` ([[paths]]): use the downloaded file or a fetcher;
- **`import`** of other files, and `<nixpkgs>`: ask for packages as arguments;
- **builtins that read the computer or the network:** `builtins.readFile`, `readDir`, `pathExists`, `getEnv`, `fetchurl`, `fetchGit` and `fetchTarball`, `path`, `storePath`, `getFlake`, `currentSystem`, and the `unsafe…` ones;
- **anything that weakens the build sandbox:** `__noChroot`, `impureEnvVars`, `allowSubstitutes`, `requiredSystemFeatures`;
- a file that is not a function of its dependencies, or larger than 64 KB.

The editor checks this when you save; problems show as **TulsiOS** in the list below.

```nix
{ stdenv }:
stdenv.mkDerivation { pname = "ok"; version = "1"; dontUnpack = true; installPhase = "mkdir $out"; }
```

# Reading a build log
id: tulsios-build-log
keys: log
see: autopatchelf, inputs, hashes, build-systems

The end of the build log usually says what went wrong:

- `could not satisfy dependency libfoo.so.1`: a prebuilt program needs a library. Add the package that has it to `buildInputs` and the arguments ([[autopatchelf]]). Search for the package with **Ctrl+Space** after `pkgs.` or in the arguments, or with `tulsi search` in a terminal.
- `Package 'gtk+-3.0' … not found`, `Dependency "x" not found` or `Could NOT find ZLIB`: a source build is missing a library. Add it to `buildInputs`, and `pkg-config` to `nativeBuildInputs` ([[inputs]]).
- `hash mismatch … got: sha256-…`: copy the `got:` hash in ([[hashes]]).
- `command not found`: a build tool is missing from `nativeBuildInputs`.
- `undefined variable 'x'`: `x` is not an argument of the file, or is misspelled.
- `No such file or directory` in `installPhase`: the files are somewhere else in the archive. Add `ls -R` at the start of the phase to see where.

```nix
{ stdenv, autoPatchelfHook, libX11 }:
stdenv.mkDerivation {
  pname = "frob";
  version = "1.0";
  nativeBuildInputs = [ autoPatchelfHook ];
  buildInputs = [ libX11 ];
}
```

# Build and Try, then Install
id: tulsios-build-and-install
keys:
see: tulsios-local-package, tulsios-kept, tulsios-unfree

When the editor has a Recipe's draft open:

- **Build and Try** saves, checks the file against TulsiOS's rules, builds it as you, against this computer's package collection, and starts its main program briefly in a sandbox: no network, none of your files. The log appears below.
- **Install**, once it builds, hands it to the Software Center. You see what will change and confirm, and **Undo** in the Software Center removes it again.

You can also run the same steps in a terminal: `tulsi recipe build-draft FOLDER`, then `tulsi recipe install RESULT.json`.

```nix
{ stdenv }:
stdenv.mkDerivation { pname = "hello-local"; version = "1"; dontUnpack = true; installPhase = "mkdir -p $out/bin"; }
```

# Keeping the download
id: tulsios-kept
keys: keepSource
see: tulsios-download

A local package made from a download needs that file whenever it is built again, after an upgrade for example, and TulsiOS cannot download it again by itself. By default the file is **kept** as part of the system. You can change this per package on the Software Center's Installed page.

```nix
{ keepSource = true; }
```

# Proprietary software
id: tulsios-unfree
keys: unfree, lib.licenses.unfree
see: lib-licenses, meta

Software whose licence does not let you share it is **unfree**: set `meta.license = lib.licenses.unfree;`. TulsiOS installs it only after you accept its licence, which Install asks for.

```nix
{ lib }:
{ meta.license = lib.licenses.unfree; }
```
