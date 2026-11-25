# builtins
id: builtins
keys: builtins
see: builtins-map, builtins-filter, builtins-tostring, import, lib

`builtins` holds the functions built into Nix: `map`, `filter`, `toString`, `length`, `elem`, `attrNames` and more. Some are usable without `builtins.` in front: `map`, `toString`, `import`, `throw`, `abort`, `baseNameOf`.

Most code uses [[lib]] instead, which builds on these.

TulsiOS packages may not use the builtins that read the computer or the network, such as `builtins.readFile`, `builtins.fetchurl` and `builtins.getEnv` ([[tulsios-refused]]).

```nix
builtins.length [ 1 2 3 ]
```

# map
id: builtins-map
keys: map, builtins.map, lib.map
see: builtins-filter, lists

`map f list` applies `f` to every element and returns the new list.

```nix
map (x: x * 10) [ 1 2 3 ]
```

# filter
id: builtins-filter
keys: filter, builtins.filter, lib.filter
see: builtins-map

`filter test list` keeps the elements for which `test` is `true`.

```nix
builtins.filter (x: x > 1) [ 1 2 3 ]
```

# toString
id: builtins-tostring
keys: builtins.toString
see: strings

`toString x` turns a number, path, boolean or package into a string. `"${x}"` does the same for strings and packages, but numbers need `toString`.

```nix
"version " + toString 3
```

# length, elem, head
id: builtins-lists
keys: length, elem, head, tail, builtins.length, builtins.elem, builtins.head, builtins.elemAt, elemAt
see: lists

- `builtins.length list`: how many elements
- `builtins.elem x list`: is `x` in the list
- `builtins.head list`, `builtins.elemAt list 2`: one element

```nix
builtins.elem "bin" [ "bin" "lib" ]
```

# attrNames, attrValues
id: builtins-attrs
keys: attrNames, attrValues, builtins.attrNames, builtins.attrValues, hasAttr, builtins.hasAttr, getAttr, builtins.getAttr
see: attribute-sets

`builtins.attrNames set` lists a set's names (sorted), and `builtins.attrValues set` its values in the same order.

```nix
builtins.attrNames { b = 2; a = 1; }
```

# import
id: import
keys: import
see: paths, tulsios-refused

`import ./file.nix` reads and evaluates another Nix file. TulsiOS packages are one file each and **cannot import**: importing needs a path ([[paths]]), and `import <nixpkgs>` would read the computer's channels. Ask for what you need as a function argument instead ([[function-arguments]]).

```nix
import ./other.nix
```

# throw and abort
id: throw
keys: throw, abort, builtins.throw, builtins.abort
see: assert

`throw "message"` stops evaluation with an error, for example for a platform a package does not support.

```nix
let supported = true; in
if supported then "ok" else throw "this package needs x86_64"
```
