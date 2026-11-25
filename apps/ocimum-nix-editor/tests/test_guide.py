from collections import Counter

import pytest

from ocimum_nix_editor.guide import Guide, fences, parse, spans, word_at


@pytest.fixture(scope="module")
def guide():
    return Guide.load()


def test_the_guide_loads_with_working_links(guide):
    assert len(guide.entries) >= 50
    assert guide.broken_links() == []


def test_every_entry_has_an_example(guide):
    assert [e.id for e in guide.entries if not e.example] == []


def test_no_word_leads_to_two_entries(guide):
    keys = Counter(k for e in guide.entries for k in e.keys)
    assert [k for k, n in keys.items() if n > 1] == []


@pytest.mark.parametrize("word, entry", [
    ("mkDerivation", "mkderivation"),
    ("stdenv.mkDerivation", "mkderivation"),
    ("let", "let-in"),
    ("installPhase", "phases"),
    ("lib.optionalString", "lib-optional"),
    ("requireFile", "tulsios-download"),
    ("autoPatchelfHook", "autopatchelf"),
    ("buildInputs", "inputs"),
])
def test_words_in_code_find_their_entry(guide, word, entry):
    assert guide.lookup(word, prefixes=False).id == entry


def test_shorter_beginnings_only_when_asked(guide):
    # A package name is left to nixd's hover first, then `pkgs` explains.
    assert guide.lookup("pkgs.zlib", prefixes=False) is None
    assert guide.lookup("pkgs.zlib").id == "pkgs"
    assert guide.lookup("lib.licenses.mit").id == "lib-licenses"
    assert guide.lookup("nothing.here") is None


def test_search_puts_names_first(guide):
    assert guide.search("hash")[0].id == "hashes"
    assert guide.search("fetchurl")[0].id == "fetchers"
    assert guide.search("") == guide.entries
    assert guide.search("zzzz-nothing") == []


def test_snippets_for_completion(guide):
    found = {(k, e.id) for k, e in guide.snippets("mkD")}
    assert ("mkDerivation", "mkderivation") in found
    assert guide.snippets("m") == []


def test_word_at():
    line = "  buildInputs = [ pkgs.zlib lib.licenses.mit ];"
    assert word_at(line, 5) == "buildInputs"
    assert word_at(line, 22) == "pkgs.zlib"
    assert word_at(line, 2) == "buildInputs"
    assert word_at(line, 16) == ""


SAMPLE = """# One
id: one
keys: a, "b"
see: two

Text with `code`, **bold** and [[two|a link]].

## Part
- a point

```nix
{ x = 1; }
```

# Two
id: two

```nix snippet
x
```
"""


def test_parse_and_render():
    one, two = parse(SAMPLE, topic="t")
    assert (one.id, one.keys, one.see, one.topic) == ("one", ["a", "b"], ["two"], "t")
    assert one.example == "{ x = 1; }" and one.snippet == ""
    assert two.example == "x" and two.snippet == "x"
    runs = spans(one, {"two": "Two"})
    texts = {(text, tags, link) for text, tags, link in runs}
    assert ("One\n", ("title",), "") in texts
    assert ("code", ("code",), "") in texts
    assert ("bold", ("bold",), "") in texts
    assert ("a link", ("link",), "two") in texts
    assert ("Part\n", ("heading",), "") in texts
    assert ("{ x = 1; }\n", ("codeblock",), "") in texts
    assert ("Two", ("link",), "two") in texts  # See also, by title
    assert fences(one.body) == [("nix", "{ x = 1; }")]


def test_an_entry_needs_an_id():
    with pytest.raises(ValueError):
        parse("# No id\n\ntext\n")
