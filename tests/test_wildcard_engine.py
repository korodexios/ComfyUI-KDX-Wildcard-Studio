"""KDX wildcard engine (kdx_console/wildcard_engine.py) — syntax and library loading."""

import collections
import os
import time

import _helpers  # noqa: F401  (puts the package on sys.path)
import pytest

from kdx_console.wildcard_engine import CachedLibrary, Library, normalize_key, parse_weight


def lib(**m):
    return Library.from_mapping({k.replace("__", "/"): v for k, v in m.items()})


def many(library, text, n=400):
    return collections.Counter(library.expand(text, seed).text for seed in range(n))


# ----------------------------------------------------------------------------- tokens


def test_exact_token_picks_one_line():
    L = lib(color=["red", "green", "blue"])
    assert set(many(L, "__color__")) == {"red", "green", "blue"}


def test_same_seed_same_result_and_seeds_differ():
    L = lib(color=["red", "green", "blue"], size=["s", "m", "l"])
    t = "a __size__ __color__ {cat|dog}"
    assert L.expand(t, 7).text == L.expand(t, 7).text
    assert len({L.expand(t, s).text for s in range(50)}) > 5


def test_each_occurrence_is_an_independent_pick():
    L = lib(color=["red", "green", "blue", "black", "white"])
    assert any(len(set(L.expand("__color__ __color__", s).text.split())) == 2 for s in range(30))


def test_keys_are_case_insensitive_and_paths_normalized():
    L = Library.from_mapping({"Person/Age Band": ["40s"]})
    assert L.expand("__PERSON/age-band__", 1).text == "40s"
    assert normalize_key("A\\B c//D") == "a/b-c/d"


def test_value_is_expanded_again():
    L = lib(person=["a __age__ woman"], age=["young"])
    assert L.expand("__person__", 1).text == "a young woman"


def test_short_name_pools_files_with_that_base_name():
    L = Library.from_mapping({"woman/hair": ["long"], "man/hair": ["short"], "woman/eyes": ["blue"]})
    assert set(many(L, "__hair__")) == {"long", "short"}


def test_short_name_pools_a_folder():
    L = Library.from_mapping({"pose/standing": ["stand"], "pose/sitting": ["sit"], "other": ["x"]})
    assert set(many(L, "__pose__")) == {"stand", "sit"}


def test_glob_tokens():
    L = Library.from_mapping({"woman/hair": ["long"], "man/hair": ["short"], "woman/eyes": ["blue"]})
    assert set(many(L, "__woman/*__")) == {"long", "blue"}
    assert set(many(L, "__*/hair__")) == {"long", "short"}


def test_weights_in_pooled_lookups_are_used_and_not_leaked():
    L = Library.from_mapping({"a/hair": ["9::bob"], "b/hair": ["1::bun"]})
    out = many(L, "__hair__", 1000)
    assert set(out) == {"bob", "bun"} and out["bob"] > 4 * out["bun"]


def test_missing_token_stays_as_written_and_is_reported():
    L = lib(color=["red"])
    r = L.expand("a __nope/thing__ and __color__", 1)
    assert r.text == "a __nope/thing__ and red"
    assert r.missing == ["nope/thing"]


def test_missing_token_inside_options_is_kept():
    r = lib().expand("{__nope__}", 1)
    assert r.text == "__nope__" and r.missing == ["nope"]


def test_underscores_in_key_names():
    L = Library.from_mapping({"person/age_band": ["40s"], "core/medium_pro": ["film"]})
    assert L.expand("__person/age_band__, __core/medium_pro__", 3).text == "40s, film"


# ----------------------------------------------------------------------------- weights


@pytest.mark.parametrize("raw,expected", [
    ("3::often", (3.0, "often")), ("0.5::rare", (0.5, "rare")), (".5::x", (0.5, "x")),
    ("plain", (1.0, "plain")), ("a::b", (1.0, "a::b")), ("time 10::30", (1.0, "time 10::30")),
])
def test_parse_weight(raw, expected):
    assert parse_weight(raw) == expected


def test_file_line_weights():
    L = lib(c=["9::red", "1::blue"])
    out = many(L, "__c__", 1000)
    assert set(out) == {"red", "blue"} and out["red"] > 4 * out["blue"]


def test_zero_weight_never_picked_unless_all_zero():
    assert set(many(lib(c=["0::never", "1::always"]), "__c__")) == {"always"}
    assert set(many(lib(c=["0::a", "0::b"]), "__c__")) == {"a", "b"}


# ----------------------------------------------------------------------------- options


def test_options_pick_one():
    assert set(many(lib(), "{a|b|c}")) == {"a", "b", "c"}


def test_options_with_weights_and_empty_option():
    out = many(lib(), "x{9::!|1::}", 1000)
    assert set(out) == {"x!", "x"} and out["x!"] > out["x"]


def test_options_containing_tokens():
    L = lib(color=["red"], size=["big"])
    assert set(many(L, "{__color__|__size__}")) == {"red", "big"}


def test_nested_options_innermost_first():
    assert set(many(lib(), "{a|{b|c}}")) == {"a", "b", "c"}


def test_value_with_options_is_expanded():
    L = lib(hair=["{long|short} hair"])
    assert set(many(L, "__hair__")) == {"long hair", "short hair"}


def test_multi_select_fixed_count_distinct():
    for s in range(50):
        parts = lib().expand("{2$$a|b|c|d}", s).text.split(", ")
        assert len(parts) == 2 and len(set(parts)) == 2


def test_multi_select_range_and_custom_separator():
    counts = set()
    for s in range(100):
        t = lib().expand("{1-3$$ and $$a|b|c|d}", s).text
        counts.add(len(t.split(" and ")))
    assert counts == {1, 2, 3}


def test_multi_select_upper_only_and_clamped():
    assert {len(lib().expand("{-2$$a|b|c}", s).text.split(", ")) for s in range(60)} == {1, 2}
    assert sorted(lib().expand("{5$$a|b}", 1).text.split(", ")) == ["a", "b"]


def test_multi_select_over_one_wildcard_uses_its_lines():
    L = lib(flaw=["grain", "blur", "glare", "dust"])
    for s in range(40):
        parts = L.expand("{2-3$$, $$__flaw__}", s).text.split(", ")
        assert 2 <= len(parts) <= 3 and len(set(parts)) == len(parts)
        assert set(parts) <= {"grain", "blur", "glare", "dust"}


def test_escaped_characters_are_literal():
    assert lib().expand(r"a \{b\|c\} d", 1).text == "a {b|c} d"


def test_comment_lines_in_input_are_dropped_and_lora_tags_kept():
    t = "# note\nphoto of __x__ <lora:style:0.8>\n  # another"
    assert lib(x=["cat"]).expand(t, 1).text == "photo of cat <lora:style:0.8>"


def test_recursion_is_bounded():
    L = lib(loop=["__loop__ again"])
    r = L.expand("__loop__", 1)
    assert r.text.count("again") > 10  # stopped by MAX_PASSES, did not hang


# ----------------------------------------------------------------------------- files


def write(root, rel, text):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return p


def test_from_dirs_reads_tree_comments_and_bom(tmp_path):
    write(tmp_path, "person/Age.txt", "﻿# comment\n\n30s\n2::40s\n")
    write(tmp_path, "templates/portrait.txt", "a __person/age__ woman\n")
    write(tmp_path, "notes.md", "not a wildcard")
    L = Library.from_dirs([tmp_path])
    assert L.keys() == ["person/age", "templates/portrait"]
    assert [(e.value, e.weight) for e in L.data["person/age"]] == [("30s", 1.0), ("40s", 2.0)]
    assert L.expand("__templates/portrait__", 1).text in {"a 30s woman", "a 40s woman"}


def test_first_root_wins_for_duplicate_keys(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    write(a, "x.txt", "from a\n")
    write(b, "x.txt", "from b\n")
    write(b, "y.txt", "only b\n")
    L = Library.from_dirs([a, b, tmp_path / "missing"])
    assert L.expand("__x__ __y__", 1).text == "from a only b"
    assert len(L.duplicates) == 1


def test_cached_library_reloads_on_change(tmp_path):
    p = write(tmp_path, "x.txt", "one\n")
    cache = CachedLibrary()
    assert cache.get([tmp_path]).expand("__x__", 1).text == "one"
    time.sleep(0.01)
    with open(p, "w", encoding="utf-8") as f:
        f.write("two\n")
    os.utime(p, (time.time() + 5, time.time() + 5))
    assert cache.get([tmp_path]).expand("__x__", 1).text == "two"
    write(tmp_path, "y.txt", "new\n")
    assert cache.get([tmp_path]).expand("__y__", 1).text == "new"
