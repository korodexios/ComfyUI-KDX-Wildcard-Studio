"""Template builder: bubbles (parse / serialize), ready sentences, rule checks, pool views, saving, REST."""

import json
import os

import _helpers  # noqa: F401
import pytest

from kdx_console import api, builder, wildcards
from kdx_console.store import Store
from kdx_console.wildcard_engine import Library

POOLS = {
    "core/medium_amateur": "a phone snapshot", "core/medium_pro": "an editorial photograph",
    "person/age_band": "30s\n40s", "person/ethnicity": "Irish", "person/expression_positive": "smiling",
    "person/expression_neutral": "calm", "person/expression_negative": "tired", "person/expression_soft": "soft",
    "person/expression_candid": "mid-word", "person/gaze": "on the lens", "core/mood": "quiet",
    "core/mood_somber": "heavy", "person/hair": "long and dark", "man/hair": "short", "person/eye_color": "green",
    "person/nose": "a straight nose", "person/lips": "full lips", "person/facial_imperfections": "freckles",
    "person/face_shape": "an oval face", "person/makeup": "bare", "man/facial_hair": "stubble",
    "clothing/everyday": "a grey sweater", "clothing/menswear": "a navy suit", "pose/neutral": "standing straight",
    "pose/seat_chair": "seated on a chair", "pose/lying_scene": "lying on a bed. The scene is a bedroom. This is a "
    "full shot, 3:2, shot from above. soft lamp light",
    "pose/studio_scene": "seated on a stool. The scene is a white set. This is a full shot, 4:5, shot at eye level",
    "core/place_indoor": "a kitchen", "core/place_city": "a busy street", "core/light_daylight": "soft daylight",
    "core/light_sky": "low sun", "core/shot_fashion": "a full-length shot, 4:5\n2::a waist-up shot, 4:5",
    "core/camera_angle_standing": "at eye level", "core/realism": "natural skin", "core/palette": "muted colour",
    "core/shot_none": "a wide view",
}


def lib():
    return Library.from_mapping(POOLS)


def spec(sex="woman"):
    return builder.default_spec(sex)


# ------------------------------------------------------------------ bubbles: parse / serialize


T = builder.parse_line
W = builder.serialize

LINES = [
    "",
    "plain text, no syntax at all.",
    "The image is {__core/medium_pro__}.",
    "The image is {2::__core/medium_amateur__|__core/medium_pro__|0.5::a {red|blue} toy}.",
    "{The image is __core/medium_pro__. |}It shows a woman.{ {__core/palette__}.|}",
    "{1-2$$ $$Her eyes are __person/eye_color__.|She has __person/nose__.}",
    "{2$$__person/hair__|__man/hair__} and {-3$$ and $$a|b|c} and {$$a|b} and {2-3$$, $$__person/hair__}",
    "{5::Her expression is {2::__person/expression_positive__|1::__person/expression_candid__}. The mood is "
    "{__core/mood__}|2::sad {__core/mood_somber__}}.",
    "escaped \\{ brace \\} and a | bar outside, {a\\|b|c}",
    "a lone { brace and a lone } brace",
    "__light__ and __person/*__ stay as written <lora:x:1>",
    "100:: is not a weight outside a group, {3::}",
]


@pytest.mark.parametrize("line", LINES)
def test_parse_serialize_round_trip(line):
    nodes = T(line)
    assert W(nodes) == line
    assert W(builder.normalize_nodes(json.loads(json.dumps(nodes)))) == line


def test_parse_shapes():
    n = T("The image is {3::__core/medium_pro__|a {red|blue} toy}.")
    assert n[0] == {"t": "text", "v": "The image is "} and n[2] == {"t": "text", "v": "."}
    g = n[1]
    assert g["t"] == "choice" and g["count"] is None and g["sep"] is None
    assert g["opts"][0] == {"w": "3", "items": [{"t": "pool", "name": "core/medium_pro"}]}
    assert g["opts"][1]["w"] is None and g["opts"][1]["items"][1]["t"] == "choice"
    some = T("{x|}")[0]
    assert some["opts"][1] == {"w": None, "items": []}
    multi = T("{1-2$$ $$a|b}")[0]
    assert (multi["count"], multi["sep"]) == ("1-2", " ")
    assert T("{2$$a|b}")[0]["sep"] is None
    assert T("a { b")[1] == {"t": "raw", "v": "{"}
    assert T("x \\{y\\}")[0] == {"t": "text", "v": "x {y}"}


def test_text_is_escaped_where_it_would_be_syntax():
    nodes = [{"t": "text", "v": "a {b} | c "}, {"t": "choice", "count": None, "sep": None,
                                                "opts": [{"w": None, "items": [{"t": "text", "v": "x|y"}]},
                                                         {"w": "2", "items": []}]}]
    line = W(nodes)
    assert line == "a \\{b\\} | c {x\\|y|2::}"
    assert lib().expand(line, 1).text.startswith("a {b} | c ")


def test_parse_matches_the_engine():
    """Bubbles say what the engine does: the same line from bubbles expands the same."""
    lb = lib()
    for line in LINES:
        for seed in range(5):
            assert lb.expand(W(T(line)), seed).text == lb.expand(line, seed).text


def test_normalize_rejects_bad_bubbles():
    bad = [
        [{"t": "pool", "name": "a__b"}], [{"t": "pool", "name": ""}], [{"t": "nope"}],
        [{"t": "text", "v": "two\nlines"}], [{"t": "choice", "opts": []}],
        [{"t": "choice", "opts": [{"w": "x", "items": []}]}], [{"t": "choice", "count": "a", "opts": [{"items": []}]}],
        [{"t": "choice", "count": "1", "sep": "|", "opts": [{"items": []}]}], "not a list",
    ]
    for nodes in bad:
        with pytest.raises(builder.BuilderError):
            builder.normalize_nodes(nodes)
    deep = []
    for _ in range(40):
        deep = [{"t": "choice", "opts": [{"items": deep}]}]
    with pytest.raises(builder.BuilderError):
        builder.normalize_nodes(deep)
    assert builder.normalize_nodes([{"t": "text", "v": ""}, {"t": "pool", "name": "core/mood", "x": 1}]) == \
        [{"t": "pool", "name": "core/mood"}]


@pytest.mark.parametrize("sex", ["woman", "man", "none"])
def test_starters_and_snippets(sex):
    assert W(builder.starter(sex)) == builder.compose(spec(sex))
    sn = builder.snippets()[sex]
    ids = [s["id"] for s in sn]
    assert "medium" in ids and "palette" in ids
    assert ("expression" in ids) == (sex != "none")
    for s in sn:
        line = W(s["nodes"])
        assert line and not line.startswith(" ") and "  " not in line
    if sex == "woman":
        expr = W(next(s for s in sn if s["id"] == "expression")["nodes"])
        assert "The mood is {__core/mood__}" in expr and "{__core/mood_somber__}" in expr
        scene = W(next(s for s in sn if s["id"] == "pose_mode")["nodes"])
        assert scene == "She is {__pose/studio_scene__}."


# ------------------------------------------------------------------ sentences (the blocks behind the snippets)


def test_glue_and_weights():
    sp = spec()
    sp["blocks"]["medium"]["slots"]["main"] = [{"key": "core/medium_pro", "w": 3}, {"key": "core/medium_amateur"}]
    text = builder.compose(sp)
    assert text.startswith("The image is {3::__core/medium_pro__|__core/medium_amateur__}. It shows a woman in her ")
    assert "She is wearing {__clothing/everyday__}. She is posed {__pose/neutral__}." in text
    assert "This is {__core/shot_fashion__}, shot {__core/camera_angle_standing__}." in text
    man = builder.compose(spec("man"))
    assert "It shows a man in his" in man and "His hair is {__man/hair__}." in man


def test_expression_and_mood_are_picked_together():
    text = builder.compose(spec())
    assert ("{5::Her expression is {__person/expression_positive__} and her gaze is {__person/gaze__}. The mood is "
            "{__core/mood__}|3::") in text
    assert "|2::Her expression is {__person/expression_negative__} and her gaze is {__person/gaze__}. The mood is " \
        "{__core/mood_somber__}}." in text


def test_optional_blocks_never_double_space():
    sp = spec()
    for bid in ("medium", "person", "light", "palette"):
        sp["blocks"][bid]["optional"] = True
    text = builder.compose(sp)
    assert text.startswith("{The image is ") and " |}{It shows" in text and text.endswith("{ {__core/palette__}.|}")
    lb = lib()
    for seed in range(40):
        out = lb.expand(text, seed).text
        assert "  " not in out and not out.startswith(" ") and ".." not in out


def test_pose_leads_and_scene_bundle():
    sp = spec()
    sp["blocks"]["pose"]["slots"]["main"] = [{"key": "pose/neutral", "w": 2}, {"key": "pose/seat_chair", "w": 1}]
    assert "She is {2::posed __pose/neutral__|__pose/seat_chair__}." in builder.compose(sp)
    sp["blocks"]["pose"]["opts"]["mode"] = "scene"
    sp["blocks"]["pose"]["slots"]["main"] = [{"key": "pose/studio_scene", "w": 1}]
    text = builder.compose(sp)
    assert "The scene is" not in text and "This is" not in text and "{__core/light_daylight__}" in text
    sp["blocks"]["pose"]["slots"]["main"] = [{"key": "pose/lying_scene", "w": 1}]
    assert "light_daylight" not in builder.compose(sp)  # lying_scene carries its light


def test_normalize_spec_rejects_partial_tokens():
    sp = spec()
    sp["blocks"]["light"]["slots"]["main"] = [{"key": "light"}]
    with pytest.raises(builder.BuilderError):
        builder.compose(sp)

# ------------------------------------------------------------------ checks


def codes(text, name="", lb=None):
    return {w["code"] for w in builder.check(text, lb or lib(), name, samples=60)}


def test_default_template_passes_every_check():
    for sex in ("woman", "man"):
        sp = spec(sex)
        assert builder.check(builder.compose(sp), lib(), f"x_{sex}", samples=60) == []


def test_check_ratio():
    sp = spec()
    sp["blocks"]["shot"]["slots"]["shot"] = [{"key": "core/shot_none", "w": 1}]
    assert "ratio" in codes(builder.compose(sp))
    sp["blocks"]["shot"]["on"] = False
    assert "ratio" in codes(builder.compose(sp))
    sp = spec()
    sp["blocks"]["pose"]["opts"]["mode"] = "scene"
    sp["blocks"]["pose"]["slots"]["main"] = [{"key": "pose/studio_scene", "w": 1}]
    assert "ratio" not in codes(builder.compose(sp))  # the bundle carries the shot


def test_check_nsfw_clothing():
    sp = spec()
    text = builder.compose(sp)
    got = codes(text, "akt_new")
    assert {"clothing", "clothing_words", "soft"} <= got
    sp["blocks"]["clothing"]["on"] = False
    sp["blocks"]["expression"]["opts"]["family"] = "soft"
    assert not ({"clothing", "clothing_words", "soft"} & codes(builder.compose(sp), "nsfw_new"))
    assert "clothing" not in codes(text, "portrait")


def test_check_sky_light_only_outdoors():
    sp = spec()
    sp["blocks"]["light"]["slots"]["main"] = [{"key": "core/light_sky", "w": 1}]
    assert "sky" in codes(builder.compose(sp))
    sp["blocks"]["place"]["slots"]["main"] = [{"key": "core/place_city", "w": 1}]
    assert "sky" not in codes(builder.compose(sp))
    sp["blocks"]["pose"]["opts"]["mode"] = "scene"  # a studio bundle is indoors although it names no place pool
    sp["blocks"]["pose"]["slots"]["main"] = [{"key": "pose/studio_scene", "w": 1}]
    assert "sky" in codes(builder.compose(sp))


def test_check_expression_needs_mood_and_tokens_and_lines():
    assert "mood" in codes("Her expression is {__person/expression_positive__}. This is {__core/shot_fashion__}.")
    assert "full_token" in codes("{__light__}. This is {__core/shot_fashion__}.")
    assert "unknown" in codes("{__core/nothing_here__}.")
    assert "one_line" in codes("a\nb")
    assert codes("") == {"empty"}
    assert "spaces" in codes("This is  {__core/shot_fashion__}.")


def test_check_name_follows_sex():
    sp = spec("man")
    assert "sex_name" in codes(builder.compose(sp), "street_woman")
    assert "sex_name" not in codes(builder.compose(sp), "street_man")


# ------------------------------------------------------------------ library views


def test_pool_index_and_usage():
    lb = Library.from_mapping({**POOLS, "templates/demo": "x {__core/light_sky__}", "templates/akt_x": "__core/mood__"})
    idx = {p["key"]: p for p in builder.pool_index(lb)}
    assert "templates/demo" not in idx
    assert idx["core/light_sky"]["templates"] == ["demo"] and idx["core/shot_fashion"]["count"] == 2
    d = builder.pool_detail(lb, "core/mood", hide=wildcards.is_excluded)
    assert d["templates"] == [] and d["hidden_templates"] == 1
    assert builder.pool_detail(lb, "core/shot_fashion")["values"][1] == {"value": "a waist-up shot, 4:5", "w": 2.0}
    with pytest.raises(builder.BuilderError):
        builder.pool_detail(lb, "templates/demo")


def test_preview_samples():
    text = builder.compose(spec())
    a = builder.preview(text, lib(), 3, seed=7)
    assert len(a) == 3 and a == builder.preview(text, lib(), 3, seed=7)
    assert all("__" not in s["text"] and not s["missing"] for s in a)


# ------------------------------------------------------------------ saving


def test_write_template(tmp_path):
    res = builder.write_template(str(tmp_path), "demo_woman", "The image is {__core/medium_pro__}.")
    path = tmp_path / "templates" / "demo_woman.txt"
    assert res["created"] and path.read_text(encoding="utf-8") == "The image is {__core/medium_pro__}.\n"
    with pytest.raises(FileExistsError):
        builder.write_template(str(tmp_path), "demo_woman", "x.")
    path.write_text("# keep me\nold line\n", encoding="utf-8")
    res = builder.write_template(str(tmp_path), "demo_woman", "new line.", overwrite=True)
    assert res["backup"] and (tmp_path / "templates" / "demo_woman.txt.bak").read_text(encoding="utf-8") == \
        "# keep me\nold line\n"
    assert path.read_text(encoding="utf-8") == "# keep me\nnew line.\n"
    for bad in ("../x", "Bad", "a b", ""):
        with pytest.raises(builder.BuilderError):
            builder.write_template(str(tmp_path), bad, "x.")
    with pytest.raises(builder.BuilderError):
        builder.write_template(str(tmp_path), "two", "a\nb")


# ------------------------------------------------------------------ REST handlers


@pytest.fixture
def env(tmp_path, monkeypatch):
    wc = tmp_path / "wc"
    for key, text in POOLS.items():
        p = wc / (key + ".txt")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("# description of " + key + "\n" + text + "\n", encoding="utf-8")
    (wc / "templates").mkdir()
    (wc / "templates" / "old_hand.txt").write_text("{__core/light_sky__}, by hand\n", encoding="utf-8")
    (wc / "templates" / "akt_hidden.txt").write_text("{__core/mood__}\n", encoding="utf-8")
    monkeypatch.delenv(wildcards.ENV_DIRS, raising=False)
    monkeypatch.setattr(wildcards, "_dirs_provider", lambda: [str(wc)])
    store = Store(str(tmp_path / "kdx_console"))
    store.save_config({"categories": [{"key": "mine", "name": "Mine", "templates": []}], "ignored": ["fresh_woman"]})
    return store, wc


def body(d):
    return json.dumps(d).encode()



def test_api_builder_index(env):
    store, _wc = env
    status, d = api.get_builder(store)
    assert status == 200 and d["ok"]
    pools = {p["key"]: p for p in d["pools"]}
    assert pools["core/light_sky"]["templates"] == ["old_hand"] and pools["core/mood"]["templates"] == []
    assert pools["core/mood"]["desc"] == "description of core/mood"
    assert "akt_hidden" not in d["templates"] and "old_hand" in d["templates"]
    assert set(d["snippets"]) == {"woman", "man", "none"} and builder.serialize(d["starters"]["man"])
    status, d = api.get_builder_pool(store, {"key": "core/shot_fashion"})
    assert status == 200 and d["pool"]["count"] == 2 and d["pool"]["head"] == ["description of core/shot_fashion"]
    assert api.get_builder_pool(store, {"key": "nope/x"})[0] == 400


def test_api_template_opens_as_bubbles(env):
    store, wc = env
    status, d = api.get_builder_template(store, {"name": "old_hand"})
    assert status == 200 and d["text"] == "{__core/light_sky__}, by hand" and not d["note"] and d["categories"] == []
    assert d["nodes"][0]["t"] == "choice" and d["nodes"][1] == {"t": "text", "v": ", by hand"}
    (wc / "templates" / "two_lines.txt").write_text("# c\nfirst __core/mood__\nsecond\n", encoding="utf-8")
    status, d = api.get_builder_template(store, {"name": "two_lines"})
    assert d["text"] == "{first __core/mood__|second}" and "2 lines" in d["note"]
    assert api.get_builder_template(store, {"name": "akt_hidden"})[0] == 400
    assert api.get_builder_template(store, {"name": "missing"})[0] == 400


def test_api_parse(env):
    store, _wc = env
    status, d = api.post_builder_parse(store, body({"text": "a {b|c}\nd"}))
    assert status == 200 and d["text"] == "a {b|c} d" and builder.serialize(d["nodes"]) == "a {b|c} d"


def test_api_preview(env):
    store, _wc = env
    nodes = builder.starter("woman")
    status, d = api.post_builder_preview(store, body({"nodes": nodes, "name": "x_woman", "count": 3, "seed": 1}))
    assert status == 200 and d["text"] == builder.compose(spec()) and len(d["samples"]) == 3 and d["warnings"] == []
    status, d = api.post_builder_preview(store, body({"nodes": T("{__light__}.")}))
    assert status == 200 and "full_token" in {w["code"] for w in d["warnings"]}
    status, d = api.post_builder_preview(store, body({"nodes": [{"t": "pool", "name": "x__y"}]}))
    assert status == 400 and "pool name" in d["error"]
    status, d = api.post_builder_preview(store, body({"nodes": []}))
    assert status == 200 and {w["code"] for w in d["warnings"]} == {"empty"} and d["samples"] == []


def test_api_save_new_overwrite_and_category(env):
    store, wc = env
    nodes = builder.starter("woman")
    line = builder.serialize(nodes)
    status, d = api.post_builder_save(store, body({"name": "fresh_woman", "nodes": nodes, "category": "mine"}))
    assert status == 200 and d["created"] and d["category"] == "mine"
    path = wc / "templates" / "fresh_woman.txt"
    assert path.read_text(encoding="utf-8").strip() == line
    cfg = store.load_config()
    assert [t["name"] for t in cfg["categories"][0]["templates"]] == ["fresh_woman"]
    assert "fresh_woman" not in cfg["ignored"]
    nodes2 = nodes + [{"t": "text", "v": " My own words."}]
    status, d = api.post_builder_save(store, body({"name": "fresh_woman", "nodes": nodes2}))
    assert status == 409 and d["exists"] and path.read_text(encoding="utf-8").strip() == line
    status, d = api.post_builder_save(store, body({"name": "fresh_woman", "nodes": nodes2, "overwrite": True,
                                                   "category": "mine"}))
    assert status == 200 and d["backup"] and not d["created"] and d["category"] is None  # already there
    assert os.path.exists(str(path) + ".bak")
    assert path.read_text(encoding="utf-8").strip() == line + " My own words."
    status, d = api.get_builder_template(store, {"name": "fresh_woman"})
    assert builder.serialize(d["nodes"]) == line + " My own words."
    assert d["categories"] == ["mine"]  # Save as in the panel keeps a copy in the same category
    assert api.post_builder_save(store, body({"name": "x_woman", "nodes": nodes, "category": "nope"}))[0] == 400
    assert api.post_builder_save(store, body({"name": "../evil", "nodes": T("x.")}))[0] == 400
    assert api.post_builder_save(store, body({"name": "empty_one", "nodes": []}))[0] == 400


def test_every_line_of_the_bundled_library_round_trips():
    lb = Library.from_dirs([wildcards.STARTER_DIR])
    lines = [e.value for entries in lb.data.values() for e in entries]
    assert len(lines) > 50
    for line in lines:
        assert W(T(line)) == line, line
