"""Keep parts: the traced expansion is the same as the plain one, the record takes the prompt apart into the
picks that made it, and kept parts give a template whose other parts still vary."""

import json
import os
import random

import _helpers  # noqa: F401
import pytest

from kdx_console import api, keep, wildcards
from kdx_console.store import Store
from kdx_console.wildcard_engine import Library

STARTER = os.path.join(_helpers.ROOT, "starter_wildcards")

LIB = {
    "person/hair": ["long and dark", "short and red", "2::grey curls"],
    "person/expression_positive": ["smiling", "laughing"],
    "person/expression_negative": ["tired", "annoyed"],
    "core/mood": ["quiet", "bright"],
    "core/mood_somber": ["heavy", "grey"],
    "core/medium": ["a photo of __core/gear__", "a painting"],
    "core/gear": ["a Leica", "a phone"],
    "clothing/top": ["a {red|blue} shirt", "a coat"],
    "core/place": ["a kitchen", "a street"],
    "core/light_sky": ["low sun", "overcast"],
    "templates/portrait": [
        "__core/medium__. Her hair is __person/hair__, {3::her expression is {__person/expression_positive__}. "
        "The mood is {__core/mood__}|her expression is {__person/expression_negative__}. The mood is "
        "{__core/mood_somber__}}. She wears __clothing/top__ in __core/place__, {__core/light_sky__|}.",
        "a second line with __person/hair__",
    ],
}


def lib():
    return Library.from_mapping(LIB)


# ------------------------------------------------------------------ the same picks as without a record


def test_trace_gives_the_same_text_for_every_seed():
    lb = lib()
    texts = ["__templates/portrait__", "{2$$ and $$a|b|__person/hair__}", "{1-3$$__person/hair__}",
             "x \\{literal\\} __missing/pool__ {a|{b|{c|d}}} {|e}", "__person/*__ __hair__"]
    for text in texts:
        for seed in range(300):
            assert lb.expand(text, seed, trace=True).text == lb.expand(text, seed).text, (text, seed)


def test_trace_matches_on_the_starter_library():
    """The bundled library: every template, many seeds, the same text and a record that passes its checks."""
    lb = Library.from_dirs([STARTER])
    names = [k for k in lb.keys() if k.startswith("templates/")]
    assert names
    rng = random.Random(1)
    for key in names:
        for _ in range(25):
            seed = rng.randrange(2**31)
            plain = lb.expand(f"__{key}__", seed).text
            d = keep.decompose(lb, f"__{key}__", seed)
            assert d.prompt == plain
            assert d.reliable(lb), (key, seed)


def test_store_run_seed_gives_the_stored_prompt(tmp_path):
    """What a run stores (template + seed) takes apart into exactly the prompt of that run."""
    lb = lib()
    store = Store(str(tmp_path), seed_fn=_helpers.SeqSeeds())
    store.save_config(_helpers.cfg(("people", [("portrait", 3)])))
    res = store.run(lambda token, seed: lb.expand(token, seed).text)
    d = keep.decompose(lb, f"__templates/{res.plan.template}__", res.plan.seed)
    assert d.prompt == res.prompt
    assert keep.compare(res.prompt, d.prompt) is True


# ------------------------------------------------------------------ the record


def _find(d, name):
    return [p for p in d.walk() if p.kind == "token" and p.name == name]


def _seed_with(lb, text, want):
    for seed in range(2000):
        if all(w in lb.expand(text, seed).text for w in want):
            return seed
    raise AssertionError(want)


def test_parts_cover_the_prompt_and_nest():
    lb = lib()
    seed = _seed_with(lb, "__templates/portrait__", ["photo of", "expression"])
    d = keep.decompose(lb, "__templates/portrait__", seed)
    assert d.text_of(d.root) == d.prompt
    gear = _find(d, "core/gear")[0]
    medium = _find(d, "core/medium")[0]
    assert medium.id in d.ancestors(gear.id)  # a value with a wildcard inside: the whole or only its part
    # the expression chosen inside the outer option stays a part of its own
    expr = [p for p in d.walk() if p.kind == "token" and "expression" in p.name]
    assert len(expr) == 1


def test_keeping_the_expression_keeps_its_option_and_varies_the_mood():
    lb = lib()
    seed = _seed_with(lb, "__templates/portrait__", ["expression is smiling"])
    d = keep.decompose(lb, "__templates/portrait__", seed)
    expr = _find(d, "person/expression_positive")[0]
    t = d.render([expr.id])
    assert "her expression is smiling" in t
    assert "__core/mood__" in t and "mood_somber" not in t  # the option is kept, the mood still varies
    assert "__person/hair__" in t  # the rest stays wildcards
    moods = {lb.expand(t, s).text.split("The mood is ")[1].split(".")[0] for s in range(40)}
    assert moods == {"quiet", "bright"}


def test_keeping_a_part_of_a_value_keeps_the_line_it_came_from():
    lb = lib()
    seed = _seed_with(lb, "__templates/portrait__", ["photo of a Leica"])
    d = keep.decompose(lb, "__templates/portrait__", seed)
    gear = _find(d, "core/gear")[0]
    medium = _find(d, "core/medium")[0]
    only_gear = d.render([gear.id])
    assert only_gear.startswith("a photo of a Leica.")
    whole = d.render([medium.id])
    assert whole.startswith("a photo of a Leica.")
    # the template line chosen by the seed is kept too: never "a second line"
    for s in range(30):
        assert lb.expand(only_gear, s).text.startswith("a photo of a Leica.")


def test_no_locks_gives_back_the_input_and_all_leaves_the_prompt():
    lb = lib()
    for seed in range(50):
        d = keep.decompose(lb, "__templates/portrait__", seed)
        assert d.render([]) == "__templates/portrait__"
        assert lb.expand(d.render(d.leaves()), 999).text == d.prompt
        assert d.reliable(lb)


def test_literal_text_is_escaped():
    lb = Library.from_mapping({"x": ["half | off {b|b}"], "y": ["one", "two"]})
    d = keep.decompose(lb, "__x__ \\{lit\\} __y__", 3)
    x = _find(d, "x")[0]
    t = d.render([x.id])
    assert d.prompt.startswith("half | off b {lit} ")
    assert lb.expand(t, 1).text.startswith("half | off b {lit} ")
    assert t.endswith("__y__")


def test_empty_option_keeps_its_place():
    lb = Library.from_mapping({"y": ["one", "two"]})
    seed = next(s for s in range(200) if lb.expand("A{x|}B __y__", s).text.startswith("AB"))
    d = keep.decompose(lb, "A{x|}B __y__", seed)
    y = _find(d, "y")[0]
    t = d.render([y.id])
    assert t.startswith("A{x|}B ")  # the empty pick was not lost


def test_redundant_and_unknown_locks_are_dropped():
    lb = lib()
    seed = _seed_with(lb, "__templates/portrait__", ["photo of"])
    d = keep.decompose(lb, "__templates/portrait__", seed)
    gear = _find(d, "core/gear")[0]
    medium = _find(d, "core/medium")[0]
    assert d.clean_locks([gear.id, medium.id, 0, 9999, "x"]) == {medium.id}


def test_groups():
    assert keep.group_of("person/hair") == "face"
    assert keep.group_of("person/expression_positive") == "face"
    assert keep.group_of("person/age_band") == "body"
    assert keep.group_of("clothing/portrait") == "clothing"
    assert keep.group_of("pose/city_scene") == "pose"
    assert keep.group_of("core/camera_angle_face") == "camera"
    assert keep.group_of("core/light_sky") == "scene"
    assert keep.group_of("core/mood") == "style"
    lb = lib()
    d = keep.decompose(lb, "__templates/portrait__", _seed_with(lb, "__templates/portrait__", ["photo of"]))
    g = {x["id"]: x["ids"] for x in d.groups()}
    assert set(g["person"]) == set(g["face"]) | set(g.get("body", []))
    assert "camera" in g  # core/gear inside core/medium: a part of its own


def test_changed_library_is_reported():
    lb = lib()
    d = keep.decompose(lb, "__templates/portrait__", 5)
    other = Library.from_mapping({**LIB, "person/hair": ["blue"]})
    d2 = keep.decompose(other, "__templates/portrait__", 5)
    assert keep.compare(d.prompt, d2.prompt) is False
    assert keep.compare("", d2.prompt) is None


# ------------------------------------------------------------------ REST


@pytest.fixture
def server(tmp_path, monkeypatch):
    root = tmp_path / "wc"
    for key, lines in LIB.items():
        path = root / (key + ".txt")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (root / "templates" / "nsfw_x.txt").write_text("__person/hair__\n", encoding="utf-8")
    store = Store(str(tmp_path / "data"), seed_fn=_helpers.SeqSeeds())
    monkeypatch.setattr(wildcards, "_dirs_provider", lambda: [str(root)])
    return store


def _post(fn, store, body):
    return fn(store, json.dumps(body).encode())


def test_rest_take_apart_and_build(server):
    lb = wildcards.library()
    prompt = lb.expand("__templates/portrait__", 11).text
    st, d = _post(api.post_keep, server, {"template": "portrait", "seed": 11, "expected": prompt})
    assert st == 200 and d["matches"] is True and d["reliable"] is True and d["prompt"] == prompt
    assert d["tree"]["segs"][0]["kind"] == "token"  # the template token, its line inside
    ids = next(g["ids"] for g in d["groups"] if g["id"] == "face")
    st, b = _post(api.post_keep_build, server, {"template": "portrait", "seed": 11, "locks": ids,
                                                "fingerprint": d["fingerprint"], "count": 4})
    assert st == 200 and len(b["samples"]) == 4
    assert b["template"] != "__templates/portrait__"
    st, b = _post(api.post_keep_build, server, {"template": "portrait", "seed": 11, "locks": ids,
                                                "fingerprint": "stale"})
    assert st == 400 and "changed" in b["error"]


def test_rest_mismatch_and_own_text(server):
    st, d = _post(api.post_keep, server, {"template": "portrait", "seed": 11, "expected": "something else"})
    assert st == 200 and d["matches"] is False
    st, d = _post(api.post_keep, server, {"text": "a cat, __person/hair__", "seed": 3})
    assert st == 200 and d["matches"] is None and d["prompt"].startswith("a cat, ")


def test_rest_nsfw_and_missing_seed(server):
    st, d = _post(api.post_keep, server, {"template": "nsfw_x", "seed": 1})
    assert st == 400 and "NSFW" in d["error"]
    st, d = _post(api.post_keep, server, {"template": "portrait"})
    assert st == 400 and "seed" in d["error"]


def test_rest_save_takes_a_line(server):
    st, d = _post(api.post_builder_save, server, {"name": "kept_one", "text": "a \\{x\\} and __person/hair__"})
    assert st == 200, d
    path = os.path.join(wildcards.resolve_dirs()[0][0], "templates", "kept_one.txt")
    with open(path, encoding="utf-8") as f:
        assert f.read().strip() == "a \\{x\\} and __person/hair__"
