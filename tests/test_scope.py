"""Per-workflow scope: own on/off over the shared config and an own counter."""

import json

import pytest
from _helpers import SeqSeeds, cfg, fake_expand

from kdx_console import api
from kdx_console import scope as scope_mod
from kdx_console.engine import ConsoleError
from kdx_console.store import Store


@pytest.fixture
def store(tmp_path):
    s = Store(str(tmp_path / "kdx_console"), seed_fn=SeqSeeds())
    s.save_config(cfg(("a", [("x", 1), ("y", 1)]), ("b", [("z", 1), ("w", 1, False)])))
    return s


def sc(channel="w_one", **set_):
    return json.dumps({"channel": channel, "set": {k.replace("__", "."): v for k, v in set_.items()}})


def test_parse_empty_is_shared():
    assert scope_mod.parse("").shared and scope_mod.parse(None).channel == "main"


@pytest.mark.parametrize("bad", ["{", "[1]", '{"channel": "a b"}', '{"set": [1]}'])
def test_parse_rejects_bad_scope(bad):
    with pytest.raises(ConsoleError):
        scope_mod.parse(bad)


def test_scope_switches_categories_and_templates_without_touching_config(store):
    s = sc(a=False, b__w=True)
    seen = [store.run(fake_expand, scope=s).plan.template for _ in range(3)]
    assert seen == ["z", "w", "z"]
    assert [t["enabled"] for t in store.load_config()["categories"][1]["templates"]] == [True, False]
    assert store.load_config()["categories"][0]["enabled"] is True


def test_each_workflow_has_its_own_counter(store):
    one, two = sc("w_one"), sc("w_two")
    assert [store.run(fake_expand, scope=one).plan.template for _ in range(2)] == ["x", "y"]
    assert store.run(fake_expand, scope=two).plan.template == "x"
    assert store.run(fake_expand).plan.template == "x"  # shared counter untouched
    chans = store.load_state()["channels"]
    assert chans["w_one"]["runs"] == 2 and chans["w_two"]["runs"] == 1 and chans["main"]["runs"] == 1


def test_unknown_keys_are_ignored(store):
    assert store.run(fake_expand, scope=sc(gone=False, a__nope=False)).plan.template == "x"


def test_overrides_win_over_scope(store):
    assert store.run(fake_expand, scope=sc(a=False), overrides="a=on, b=off").plan.template == "x"


def test_fingerprint_depends_on_scope(store):
    assert store.fingerprint(scope=sc(a=False)) != store.fingerprint(scope=sc(b=False))


def test_api_snapshot_skip_reset_select_use_the_scope(store):
    s = sc("w_api", a=False)
    st, d = api.get_state(store, {"scope": s})
    assert st == 200 and d["channel"] == "w_api" and d["preview"]["upcoming"][0]["template"] == "z"
    st, d = api.post_skip(store, json.dumps({"scope": s}).encode())
    assert st == 200 and d["channel"] == "w_api"
    st, d = api.post_select(store, json.dumps({"category": "b", "template": "z", "scope": s}).encode())
    assert d["state"]["template"] == "z"
    st, d = api.post_reset(store, json.dumps({"scope": s}).encode())
    assert d["state"]["runs"] == 0
    assert api.get_state(store, {})[1]["channel"] == "main"


def test_api_bad_scope_is_a_readable_error(store):
    st, d = api.get_state(store, {"scope": "{"})
    assert st == 400 and "scope" in d["error"]
