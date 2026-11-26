"""Node, REST handlers, import, metadata embedding, package load."""

import importlib.util
import json
import os
import sys

import pytest
from _helpers import ROOT, SeqSeeds, cfg, fake_expand

from kdx_console import api, embed, importer, nodes, profiles, wildcards
from kdx_console.engine import ConsoleError
from kdx_console.store import Store


@pytest.fixture
def store(tmp_path, monkeypatch):
    s = Store(str(tmp_path / "kdx_console"), seed_fn=SeqSeeds())
    s.save_config(cfg(("a", [("x", 2), ("y", 1)]), ("b", [("z", 1)])))
    monkeypatch.setattr(nodes, "_STORE", s)
    monkeypatch.setattr(wildcards, "expand", fake_expand)
    prompts = tmp_path / "system_prompts.json"
    prompts.write_text(json.dumps({"version": 1, "prompts": {"sp_a": {"prompt": "SYS A"}}}), encoding="utf-8")
    monkeypatch.setenv("KDX_LLM_PROMPTS_FILE", str(prompts))
    return s


def workflow(uid=7, widgets=None):
    return {"workflow": {"nodes": [{"id": 3, "type": "Other", "widgets_values": ["keep"]},
                                   {"id": uid, "type": "KDX_Console", "widgets_values": widgets or [""]}]}}


def run_node(**kw):
    return nodes.KDX_Console().run(**kw)


# ---------------------------------------------------------------- node

def test_node_outputs_and_types(store):
    out = run_node(pin="", unique_id="7", extra_pnginfo=workflow())
    res = out["result"]
    assert len(res) == len(nodes.KDX_Console.RETURN_TYPES) == len(nodes.KDX_Console.RETURN_NAMES)
    prompt, sp, cat, tpl, idx, left, llm, state_json = res
    assert (prompt, sp, cat, tpl, idx, left, llm) == (f"T:x#{json.loads(state_json)['seed']}", "", "a", "x", 1, 1,
                                                       False)
    assert "*" not in nodes.KDX_Console.RETURN_TYPES
    assert "A › x · 1/2" in out["ui"]["kdx_console"][0]["summary"]


def test_node_llm_enabled_outputs_system_prompt(store):
    raw = store.load_config()
    raw["llm_enabled"] = True
    store.save_config(raw)
    res = run_node(pin="")["result"]
    assert (res[1], res[6]) == ("SYS A", True)


def test_llm_enabled_output_follows_panel_and_overrides(store):
    assert nodes.KDX_Console.RETURN_NAMES == ("prompt", "system_prompt", "category", "template", "index",
                                              "repeat_left", "llm_enabled", "state_json")
    raw = store.load_config()
    raw["llm_enabled"] = True
    store.save_config(raw)
    assert run_node(pin="", overrides="")["result"][6] is True
    assert run_node(pin="", overrides="llm=off")["result"][6] is False


def test_unknown_profile_is_clear_error_and_no_advance(store):
    raw = store.load_config()
    raw["llm_enabled"] = True
    raw["categories"][0]["system_prompt"] = "missing"
    store.save_config(raw)
    with pytest.raises(ConsoleError, match="missing"):
        run_node(pin="")
    assert store.load_state()["channels"]["main"]["runs"] == 0


def test_is_changed_differs_per_run_never_nan(store):
    a = nodes.KDX_Console.IS_CHANGED(pin="", overrides=None)
    run_node(pin="")
    b = nodes.KDX_Console.IS_CHANGED(pin="", overrides=None)
    assert a != b and "nan" not in (a + b).lower()
    assert nodes.KDX_Console.IS_CHANGED(pin="", overrides="bad").startswith(("error:", ""))


def test_overrides_via_wire(store):
    res = run_node(pin="", overrides="a=off")["result"]
    assert res[3] == "z"
    res = run_node(pin="", overrides="select=a.y")["result"]
    assert res[3] == "y"


def test_pin_roundtrip_through_image_metadata(store):
    info = workflow()
    first = run_node(pin="", unique_id="7", extra_pnginfo=info)["result"]
    pin_json = info["workflow"]["nodes"][1]["widgets_values"][0]
    assert info["workflow"]["nodes"][0]["widgets_values"] == ["keep"]
    assert info["kdx_console"]["template"] == "x"
    run_node(pin="")  # counter moves on meanwhile
    again = run_node(pin=pin_json)["result"]
    assert again[0] == first[0] and again[3] == first[3] and again[4] == first[4]


def test_input_contract_is_stable():
    it = nodes.KDX_Console.INPUT_TYPES()
    assert list(it["required"]) == ["pin"]
    # widgets_values are positional: [pin, scope, user_text, use_user_text]; new inputs only at the end
    assert list(it["optional"]) == ["overrides", "scope", "user_prompt", "user_text", "use_user_text"]
    assert it["optional"]["user_prompt"][1].get("forceInput") is True
    assert "forceInput" not in it["optional"]["scope"][1]
    assert it["optional"]["overrides"][1].get("forceInput") is True
    assert it["hidden"] == {"unique_id": "UNIQUE_ID", "extra_pnginfo": "EXTRA_PNGINFO"}


def test_user_prompt_socket_replaces_template_and_keeps_counter(store):
    info = workflow()
    out = run_node(pin="", user_prompt="  a red fox in snow  ", unique_id="7", extra_pnginfo=info)
    prompt, sp, cat, tpl, idx, left, llm, used = out["result"]
    assert (prompt, sp, cat, tpl, llm) == ("a red fox in snow", "", "user", "user_prompt", False)
    assert store.load_state()["channels"]["main"]["runs"] == 0
    assert info["kdx_console"]["prompt"] == "a red fox in snow"
    assert json.loads(info["workflow"]["nodes"][1]["widgets_values"][0])["user"] is True


def test_user_prompt_empty_or_missing_uses_console(store):
    assert run_node(pin="", user_prompt="   ")["result"][3] == "x"
    assert run_node(pin="", user_prompt=None)["result"][3] == "x"  # muted / bypassed source sends nothing


def test_user_text_widget_needs_the_switch_and_socket_wins(store):
    assert run_node(pin="", user_text="typed")["result"][3] == "x"
    assert run_node(pin="", user_text="typed", use_user_text=True)["result"][0] == "typed"
    assert run_node(pin="", user_prompt="wired", user_text="typed", use_user_text=True)["result"][0] == "wired"


def test_user_prompt_wildcards_and_pin_from_image(store):
    info = workflow()
    first = run_node(pin="", user_prompt="__a__ x", unique_id="7", extra_pnginfo=info)["result"][0]
    assert first.startswith("__a__ x#")  # went through the expander with a seed
    pin_json = info["workflow"]["nodes"][1]["widgets_values"][0]
    assert run_node(pin=pin_json, user_prompt="__a__ x")["result"][0] == first
    # the image came from user text, the text is gone now: a normal Console run, no error
    assert run_node(pin=pin_json)["result"][3] == "x"


def test_is_changed_with_user_prompt(store):
    a = nodes.KDX_Console.IS_CHANGED(pin="", user_prompt="plain")
    assert a == nodes.KDX_Console.IS_CHANGED(pin="", user_prompt="plain")
    assert a != nodes.KDX_Console.IS_CHANGED(pin="", user_prompt="other")
    assert nodes.KDX_Console.IS_CHANGED(pin="", user_prompt="{a|b}") != nodes.KDX_Console.IS_CHANGED(
        pin="", user_prompt="{a|b}")


# ---------------------------------------------------------------- embed

def test_embed_skips_subgraph_and_other_types():
    info = workflow(uid=5)
    assert embed.embed(info, "12:5", "{}", {"t": 1}) is False
    assert info["kdx_console"] == {"t": 1}
    assert embed.embed(workflow(uid=9), "3", "{}", {}) is False  # id 3 is "Other"
    assert embed.embed(None, "7", "{}", {}) is False
    d = {"workflow": {"nodes": [{"id": 7, "type": "KDX_Console", "widgets_values": {"pin": ""}}]}}
    assert embed.embed(d, 7, "P", {}) and d["workflow"]["nodes"][0]["widgets_values"]["pin"] == "P"


# ---------------------------------------------------------------- import / NSFW filter

def test_filter_templates_excludes_nsfw_and_non_templates():
    keys = ["__templates/portrait__", "__templates/nsfw_x__", "__templates/akt_1__", "__templates/Sheer_y__",
            "__templates/art/cubism__", "__templates/nsfw/foo__", "__core/mood__", "__templates/portrait__"]
    assert wildcards.filter_templates(keys) == ["portrait", "art/cubism"]


def test_import_groups_by_folder_and_keeps_settings():
    base = {"schema_version": 1, "categories": [
        {"key": "templates", "name": "Moje", "on_end": "loop",
         "templates": [{"name": "portrait", "repeat": 4, "enabled": False}, {"name": "gone", "repeat": 1}]}]}
    from kdx_console import engine
    c, _ = engine.normalize_config(base)
    new, rep = importer.merge(c, ["portrait", "selfie", "art/cubism", "art/illustration"])
    cats = {x["key"]: x for x in new["categories"]}
    assert [t["name"] for t in cats["templates"]["templates"]] == ["portrait", "gone", "selfie"]
    assert cats["templates"]["templates"][0] == {"name": "portrait", "enabled": False, "repeat": 4}
    assert cats["templates"]["on_end"] == "loop"
    assert [t["name"] for t in cats["art"]["templates"]] == ["art/cubism", "art/illustration"]
    assert rep["missing"] == ["templates.gone"]
    pruned, rep2 = importer.merge(c, ["portrait"], prune=True)
    assert [t["name"] for t in pruned["categories"][0]["templates"]] == ["portrait"]
    assert rep2["removed"] == ["templates.gone"]


# ---------------------------------------------------------------- api

def test_api_state_select_skip_reset_flow(store):
    st, data = api.get_state(store, {})
    assert st == 200 and data["preview"]["upcoming"][0]["template"] == "x"
    st, data = api.post_select(store, b'{"category":"b","template":"z"}')
    assert st == 200 and data["state"]["template"] == "z"
    assert data["config"]["select"] == {"category": "b", "template": "z"}
    st, data = api.post_skip(store)
    assert data["preview"]["upcoming"][0]["template"] == "x"
    st, data = api.post_reset(store)
    assert data["state"]["runs"] == 0


def test_api_errors_are_400_with_message(store):
    assert api.post_select(store, b'{"category":"b","template":"nope"}')[0] == 400
    assert api.post_select(store, b"not json")[0] == 400
    assert api.post_config(store, b"[1]")[0] == 400
    st, data = api.get_state(store, {"overrides": "nope=off"})
    assert st == 200 and "nope" in data["preview"]["error"]


def test_api_preview_expands_first_with_stored_seed(store):
    st, data = api.get_preview(store, {"count": "3"})
    pv = data["preview"]
    assert pv["prompt"] == f"T:x#{pv['upcoming'][0]['seed']}"
    r = store.run(fake_expand)
    assert r.prompt == pv["prompt"]


def test_api_config_roundtrip_and_import(store):
    st, data = api.post_config(store, json.dumps({"config": cfg(("q", [("w", 3)]))}).encode())
    assert st == 200 and data["config"]["categories"][0]["key"] == "q"
    st, data = api.post_import(store, b"{}", names=["portrait", "nsfw_bad", "art/cubism"])
    keys = [c["key"] for c in data["config"]["categories"]]
    assert keys == ["q", "art", "templates"]
    assert all("nsfw" not in t["name"] for c in data["config"]["categories"] for t in c["templates"])


def test_profiles_names(store):
    assert profiles.names() == ["sp_a"]
    assert api.get_profiles(store)[1]["profiles"] == ["sp_a"]


def test_events_via_listener(store):
    from kdx_console import routes

    sent = []
    store.listeners.append(routes.make_listener(lambda ev, data: sent.append((ev, data))))
    store.run(fake_expand)
    assert [e for e, _ in sent] == ["kdx_console.state", "kdx_console.run"]
    assert sent[0][1]["state"]["runs"] == 1


# ---------------------------------------------------------------- package

def test_comfyui_style_import():
    name = "ComfyUI-KDX-Wildcard-Studio-loadtest"
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "__init__.py"),
                                                  submodule_search_locations=[ROOT])
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    assert module.WEB_DIRECTORY == "./web"
    assert set(module.NODE_CLASS_MAPPINGS) == set(module.NODE_DISPLAY_NAME_MAPPINGS) == {"KDX_Console", "KDX_Console_Filename"}


def test_profiles_from_prompt_files(tmp_path, monkeypatch):
    folder = tmp_path / "kdx_llm" / "system_prompts"
    folder.mkdir(parents=True)
    wild = '# Writer\n"quotes" {braces} |pipe| \\slash 🐱\n'
    (folder / "writer.md").write_bytes(wild.encode("utf-8"))
    (folder / "plain.txt").write_text("plain", encoding="utf-8")
    (folder / ".descriptions.json").write_text("{ broken", encoding="utf-8")
    legacy = tmp_path / "kdx_llm" / "system_prompts.json"
    legacy.write_text(json.dumps({"prompts": {"writer": {"prompt": "OLD"}, "only_json": {"prompt": "J"}}}),
                      encoding="utf-8")
    monkeypatch.setenv("KDX_LLM_PROMPTS_DIR", str(folder))
    monkeypatch.setenv("KDX_LLM_PROMPTS_FILE", str(legacy))
    assert profiles.names() == ["only_json", "plain", "writer"]
    assert profiles.resolve("writer") == wild  # the file wins over the old JSON
    assert profiles.resolve("only_json") == "J"
    with pytest.raises(ConsoleError, match="not found"):
        profiles.resolve("nope")


def test_queued_picks_each_keep_their_template(store):
    """Fast ▶ clicks + Run: every prompt carries select=…, so the server cursor (last click) is ignored."""
    api.post_select(store, json.dumps({"category": "b", "template": "z"}).encode())  # last click
    seen = [run_node(pin="", overrides=f"select={c}.{t}")["result"][3]
            for c, t in (("a", "x"), ("a", "y"), ("b", "z"), ("a", "x"))]
    assert seen == ["x", "y", "z", "x"]
    assert run_node(pin="")["result"][3] == "z"  # a plain Run still follows the cursor


def test_import_excluded_template_with_file_is_not_missing_nor_pruned():
    base = {"schema_version": 1, "categories": [
        {"key": "templates", "name": "T", "templates": [{"name": "portrait"}, {"name": "nsfw_x"}, {"name": "gone"}]}]}
    from kdx_console import engine
    c, _ = engine.normalize_config(base)
    _, rep = importer.merge(c, ["portrait"], existing=["portrait", "nsfw_x"])
    assert rep["missing"] == ["templates.gone"] and rep["added"] == []
    pruned, rep2 = importer.merge(c, ["portrait"], prune=True, existing=["portrait", "nsfw_x"])
    assert [t["name"] for t in pruned["categories"][0]["templates"]] == ["portrait", "nsfw_x"]
    assert rep2["removed"] == ["templates.gone"]


def test_api_import_keeps_excluded_templates_the_user_added(store):
    api.post_config(store, json.dumps({"config": cfg(("q", [("nsfw_kept", 3)]))}).encode())
    st, data = api.post_import(store, b'{"prune": true}', names=["nsfw_kept", "nsfw_new", "portrait"])
    assert st == 200 and data["report"]["missing"] == []
    names = [t["name"] for c in data["config"]["categories"] for t in c["templates"]]
    assert "nsfw_kept" in names and "nsfw_new" not in names and "portrait" in names


def test_finished_category_blocks_quietly_instead_of_failing(store, monkeypatch):
    store.save_config(cfg(("a", [("x", 1)], "stop"), ("b", [("z", 1)])))
    events = []
    store.listeners.append(lambda kind, payload: events.append((kind, payload)))
    run_node()  # renders a.x, the category is done now
    blocker = object()
    monkeypatch.setattr(nodes, "_blocker", lambda: blocker)
    out = run_node()
    assert out["result"] == tuple(blocker for _ in nodes.KDX_Console.RETURN_TYPES)
    ui = out["ui"]["kdx_console"][0]
    assert ui["finished"] is True and "is finished (on_end = stop)" in ui["summary"]
    assert any(kind == "finished" and "is finished" in p["message"] for kind, p in events)
    assert store.load_state()["channels"]["main"]["stopped"] is True  # nothing was committed


def test_finished_without_blocker_support_raises_readable_error(store, monkeypatch):
    store.save_config(cfg(("a", [("x", 1)], "stop"), ("b", [("z", 1)])))
    run_node()
    monkeypatch.setattr(nodes, "_blocker", lambda: None)
    with pytest.raises(ConsoleError, match="is finished"):
        run_node()
