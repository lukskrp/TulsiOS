# Start here: reading Nix
id: start
keys:
see: values, attribute-sets, functions, package-file

Nix is a small language for describing software. A Nix file holds **one expression**: a value, or something that computes a value. Nothing runs top to bottom like a script; Nix works out the value you asked for.

A TulsiOS package file (`package.nix`) is a **function**: it names what it needs (`stdenv`, `requireFile`, other packages) and returns a description of how to build the software, made with `stdenv.mkDerivation`.

- Put the cursor on a word in the editor and this pane explains it.
- Search above for any topic; links like [[let-in]] lead to related entries.
- After `pkgs.` or `lib.`, **Ctrl+Space** suggests package and function names.
- Problems are underlined and listed below the editor, with TulsiOS's own rules.

```nix
{ stdenv, requireFile }:

stdenv.mkDerivation {
  pname = "example";
  version = "1.0";
  src = requireFile {
    name = "example-1.0-example.tar.gz";
    hash = "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=";
    message = "Added to the Nix store by TulsiOS.";
  };
}
```

# Values
id: values
keys: true, false, null
see: strings, lists, attribute-sets, paths

The basic values:

- strings: `"hello"`, and multi-line [[indented-strings|indented strings]]
- numbers: `42`, `3.14`
- booleans: `true`, `false`
- `null`, meaning "nothing here"
- lists: `[ 1 2 3 ]`, see [[lists]]
- attribute sets: `{ a = 1; b = "x"; }`, see [[attribute-sets]]
- functions: `x: x + 1`, see [[functions]]
- paths: `./file.txt`, see [[paths]] (not allowed in TulsiOS packages)

Nix never changes a value: "changing" one makes a new value.

```nix
{ name = "frob"; size = 3; enabled = true; parts = [ "bin" "share" ]; nothing = null; }
```

# Attribute sets
id: attribute-sets
keys: attrs, attrset
see: let-in, rec, inherit, update-operator, select-or, has-attribute

An **attribute set** is a group of names and values in braces. Each line ends with `;`.

Read a value with a dot: `point.x`. Names can be nested, and `a.b.c = 1;` is short for `a = { b = { c = 1; }; };`.

Most of a package is one attribute set, given to `stdenv.mkDerivation`.

```nix
let
  point = { x = 1; y = 2; };
  meta.license = "mit";
in
point.x + point.y
```

# let … in
id: let-in
keys: let, in
see: with, rec, attribute-sets

`let` names values for use in the expression after `in`. Names only exist inside it. The order of the definitions does not matter, and they can use each other.

Package files often use `let` for a name used twice, such as the program's name.

```nix
let
  pname = "frob";
  version = "1.2";
in
"${pname}-${version}"
```

# with
id: with
keys: with
see: let-in, inherit

`with set; expression` makes every name in `set` usable without the `set.` in front. `with pkgs; [ git curl ]` is the same as `[ pkgs.git pkgs.curl ]`.

Use it sparingly: it hides where names come from, and completion and this guide work better with the full name.

```nix
let lib = { add = a: b: a + b; }; in
with lib; add 1 2
```

# inherit
id: inherit
keys: inherit
see: attribute-sets, let-in

`inherit x y;` inside a set means `x = x; y = y;`: copy names from around it. `inherit (set) a b;` copies `a` and `b` from `set`.

In packages, `inherit pname version src;` passes the names a `let` defined on to `mkDerivation`.

```nix
let
  pname = "frob";
  version = "1.0";
  info = { homepage = "https://example.org"; };
in
{ inherit pname version; inherit (info) homepage; }
```

# rec
id: rec
keys: rec
see: let-in, attribute-sets

`rec { … }` is a set whose values can use each other's names. Prefer [[let-in]], which says the same more clearly; `rec` is common in older packages.

```nix
rec {
  version = "1.0";
  name = "frob-${version}";
}
```

# Functions
id: functions
keys: ":"
see: function-arguments, package-file

A function is `argument: body`. Calling it is just a space: `f 3`. A function of two arguments is a function returning a function: `a: b: a + b`.

```nix
let
  double = x: x * 2;
  add = a: b: a + b;
in
add (double 3) 1
```

# Functions taking a set: { a, b ? 1, ... }:
id: function-arguments
keys: "...", "?"
see: functions, package-file

Most Nix functions take one attribute set and name the parts they want.

- `{ a, b }: …` needs exactly `a` and `b`.
- `b ? 1` gives `b` a default.
- `...` accepts other names too, and ignores them.

**A package file is such a function.** Its arguments are what it needs, and TulsiOS fills them in from the system's packages by name. Ask for `{ stdenv, zlib, … }:`, and the build gets that `zlib`.

```nix
let
  greet = { name, greeting ? "Hello", ... }: "${greeting}, ${name}!";
in
greet { name = "Tulsi"; }
```

# if … then … else
id: if
keys: if, then, else
see: lib-optional

`if condition then a else b` is a value, so it always needs `else`. For "this or nothing" in a list or string, [[lib-optional|lib.optional and lib.optionalString]] are shorter.

```nix
let wanted = true; in
if wanted then "yes" else "no"
```

# Strings and ${…}
id: strings
keys: "${", toString
see: indented-strings, values

Strings are in double quotes. `${…}` puts a value into a string: `"${pname}-${version}"`. A package in a string becomes its path in the Nix store, so `"${zlib}/lib"` is where zlib's libraries are.

Escape with a backslash: `\"`, `\n`, `\${` (a literal `${`).

```nix
let name = "frob"; n = 3; in
"${name} has ${toString n} parts\n"
```

# Indented strings ''…''
id: indented-strings
keys: "''"
see: strings, phases

Two single quotes start and end a multi-line string. The indentation common to all lines is removed. Build steps such as `installPhase` are written this way, because they are shell commands.

Inside one, `${x}` still inserts Nix values. Write `''${x}` for a shell variable that should stay `${x}`, and `'''` for two quotes.

```nix
let out = "$out"; in
''
  mkdir -p ${out}/bin
  echo "''${HOME}"
''
```

# Lists
id: lists
keys: "[", "++"
see: values, builtins-map

A list is values in brackets, separated by **spaces, not commas**: `[ 1 2 3 ]`. A function call inside one needs parentheses: `[ (f 1) 2 ]`. `++` joins two lists.

`buildInputs = [ zlib openssl ];` is a list of packages.

```nix
[ 1 "two" (1 + 2) ] ++ [ 4 ]
```

# The // operator
id: update-operator
keys: "//"
see: attribute-sets

`a // b` is set `a` with the names of `b` added or replaced. It is shallow: a nested set in `b` replaces the whole nested set in `a`.

```nix
{ a = 1; b = 2; } // { b = 3; c = 4; }
```

# a.b or default
id: select-or
keys: or
see: has-attribute, attribute-sets

`set.name or fallback` reads `name`, or gives `fallback` when the set has no such name.

```nix
let s = { a = 1; }; in
s.b or 0
```

# set ? name
id: has-attribute
keys:
see: select-or

`set ? name` is `true` when the set has that name.

```nix
{ a = 1; } ? a
```

# Comments
id: comments
keys: "#"
see: start

`#` starts a comment that runs to the end of the line; `/* … */` can span lines. Comments are a good place to note why you changed something in a draft.

```nix
# The upstream archive has a top-level folder.
{ a = 1; /* not used yet */ }
```

# Paths (./file)
id: paths
keys: "./"
see: tulsios-refused, tulsios-download

`./file` or `/etc/x` is a **path**: Nix reads that file from the disk when it evaluates.

**TulsiOS refuses paths in local packages.** The system is rebuilt as root, and a path could read any file on the computer. A package gets its files through a hashed source instead, such as the [[tulsios-download|downloaded file]] or [[fetchers|a fetcher]].

```nix
{ path = ./notes.txt; }
```

# Operators
id: operators
keys: "==", "!=", "&&", "||", "->"
see: if, update-operator, lists

- arithmetic: `+ - * /` (`+` also joins strings and paths)
- comparison: `== != < <= > >=`
- logic: `&& || !`, and `a -> b` (if a then b)
- `++` joins lists, `//` merges sets, `?` tests for a name

A `-` between letters is part of a name: `my-package` is one name. Put spaces around minus: `a - b`.

```nix
(1 + 2 == 3) && !(false || "a" + "b" != "ab")
```

# assert
id: assert
keys: assert
see: if

`assert condition; expression` stops with an error when the condition is false.

```nix
let version = "1.0"; in
assert version != ""; version
```
