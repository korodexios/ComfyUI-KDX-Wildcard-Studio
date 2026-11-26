"""Pool editor: keys and paths, the file model, checks, save with backup and archive, retire, REST handlers."""

import datetime
import json
import os

import _helpers  # noqa: F401
import pytest

from kdx_console import api, pools, wildcards
from kdx_console.store import Store
from kdx_console.wildcard_engine import Library

FILES = {
    "core/light_sky.txt": "# light for places that are always outdoors\n3::soft daylight\nlow sun\n",
    "core/place_city.txt": "a busy street\n",
    "core/unused.txt": "# nobody reads me\none\ntwo\n",
    "core/inner.txt": "deep value\n",
    "core/outer.txt": "outer with __core/inner__\n",
    "core/globbed.txt": "reached by a glob\n",
    "pose/city_scene.txt": "standing on steps. The scene is __core/place_city__.\n",
    "clothing/everyday.txt": "a grey sweater\n",
    "person/body.txt": "relaxed shoulders\n",
    "templates/street_woman.txt": "{__core/light_sky__}. {__core/outer__}. __pose/city_scene__.\n",
    "templates/akt.txt": "{__person/body__}, {__core/glob*__}\n",
    "templates/sheer.txt": "{__clothing/everyday__}\n",
    "packs/demo/core/x.txt": "pack value\n",
}


@pytest.fixture
def lib_dir(tmp_path, monkeypatch):
    root = tmp_path / "lib" / "wildcards"
    for rel, text in FILES.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    monkeypatch.delenv(wildcards.ENV_DIRS, raising=False)
    monkeypatch.setattr(wildcards, "_dirs_provider", lambda: [str(root)])
    return root


def lib_of(root) -> Library:
    return Library.from_dirs([str(root)])


def model(*values, desc="", key=""):
    lines = []
    for v in values:
        if isinstance(v, tuple):
            lines.append({"v": v[0], "w": v[1]})
        elif isinstance(v, dict):
            lines.append(v)
        else:
            lines.append({"v": v, "w": None})
    return {"key": key, "desc": desc, "lines": lines}


def codes(lib, key, m):
    return {w["code"] for w in pools.check(lib, key, pools.normalize_model(m))}


# ------------------------------------------------------------------ keys and paths


@pytest.mark.parametrize("bad", ["../etc/passwd", "core/../../x", "/etc/passwd", "c:\\x\\y", "core", "", "a/b c",
                                 "core/..", "templates/street_woman", "packs/demo/core/x", "core/.hidden"])
def test_bad_keys_are_refused(bad):
    with pytest.raises(pools.PoolError):
        pools.check_key(bad, new=True)


def test_good_keys():
    assert pools.check_key("core/light_window", new=True) == "core/light_window"
    assert pools.check_key("__core/light_sky__") == "core/light_sky"
    assert pools.check_key("Core/Light_Sky") == "core/light_sky"  # lower case, as the engine reads keys
    assert pools.check_key("art/sub-folder/new_pool.txt", new=True) == "art/sub-folder/new_pool"
    with pytest.raises(pools.PoolError):
        pools.check_key("core/with-dash", new=True)  # new pool names: a-z, 0-9, _ only


def test_paths_stay_inside_the_library(lib_dir, tmp_path):
    lib = lib_of(lib_dir)
    root, path = pools.pool_path([str(lib_dir)], lib, "core/light_sky")
    assert os.path.samefile(path, lib_dir / "core" / "light_sky.txt") and root == str(lib_dir)
    root, path = pools.pool_path([str(lib_dir)], lib, "core/light_new", new=True)
    assert path == os.path.join(str(lib_dir), "core", "light_new.txt")
    with pytest.raises(pools.PoolError, match="exists"):
        pools.pool_path([str(lib_dir)], lib, "core/light_sky", new=True)
    outside = tmp_path / "elsewhere.txt"
    outside.write_text("x\n", encoding="utf-8")
    lib.sources["core/light_sky"] = str(outside)  # a library entry that points out of the root
    with pytest.raises(pools.PoolError, match="not inside"):
        pools.pool_path([str(lib_dir)], lib, "core/light_sky")
    assert pools.archive_path(str(lib_dir), "core/light_sky") == \
        os.path.join(str(lib_dir.parent), "wildcards_archive", "core", "light_sky_archive.txt")


# ------------------------------------------------------------------ the file model


def test_model_round_trip(tmp_path):
    p = tmp_path / "x.txt"
    text = "# first line\n# second\n3::a value\nplain\n#keep me\n0.5::rare\n"
    p.write_text(text, encoding="utf-8")
    m = pools.read_model(str(p), "core/x")
    assert m["desc"] == "first line\nsecond"
    assert m["lines"] == [{"v": "a value", "w": "3"}, {"v": "plain", "w": None}, {"c": "keep me"},
                          {"v": "rare", "w": "0.5"}]
    assert pools.to_text(m) == text
    with pytest.raises(pools.PoolError):
        pools.normalize_model({"lines": [{"v": "two\nlines"}]})


# ------------------------------------------------------------------ checks


def test_checks(lib_dir):
    lib = lib_of(lib_dir)
    k = "core/light_sky"
    assert codes(lib, k, model("soft daylight", ("low sun", "3"))) == set()
    assert "full_stop" in codes(lib, k, model("ends with a stop."))
    assert "full_stop" not in codes(lib, "pose/city_scene", model("a sentence. The scene is __core/place_city__."))
    assert "spaces" in codes(lib, k, model("two  spaces"))
    assert "edge_space" in codes(lib, k, model(" padded"))
    assert "blank" in codes(lib, k, model("ok", ""))
    assert "duplicate" in codes(lib, k, model("same", "Same"))
    assert "weight" in codes(lib, k, model(("x", "three")))
    assert "weight" in codes(lib, k, model("2::double weighted"))
    assert "braces" in codes(lib, k, model("an {open brace"))
    assert "unknown" in codes(lib, k, model("with __core/nothing__"))
    assert "full_token" in codes(lib, k, model("with __place_city__"))
    assert "self" in codes(lib, k, model("loop __core/light_sky__"))
    assert codes(lib, k, model()) == {"empty"}
    assert codes(lib, k, model({"c": "only a comment"})) == {"empty"}


@pytest.mark.parametrize("word", ["a teen at the beach", "schoolgirl look", "a 16 year old", "aged 15", "young child"])
def test_minors_block_the_save(lib_dir, word):
    lib = lib_of(lib_dir)
    assert "minor" in codes(lib, "core/light_sky", model("fine", word))
    before = (lib_dir / "core" / "light_sky.txt").read_text(encoding="utf-8")
    with pytest.raises(pools.PoolError, match="not saved"):
        pools.save([str(lib_dir)], lib, "core/light_sky", model("fine", word))
    assert (lib_dir / "core" / "light_sky.txt").read_text(encoding="utf-8") == before
    assert not (lib_dir / "core" / "light_sky.txt.bak").exists()


def test_clothing_warns_only_for_nsfw_users(lib_dir):
    lib = lib_of(lib_dir)
    assert "clothing" in codes(lib, "person/body", model("a lace bra"))       # read by akt
    assert "clothing" in codes(lib, "core/globbed", model("a lace bra"))      # akt reads it through a glob
    assert "clothing" not in codes(lib, "clothing/everyday", model("a coat"))  # only sheer (deliberate exception)
    assert "clothing" not in codes(lib, "core/light_sky", model("a coat"))    # SFW only


def test_users_include_globs_and_pools(lib_dir):
    lib = lib_of(lib_dir)
    assert pools.users(lib, "core/globbed")["templates"] == ["akt"]
    u = pools.users(lib, "core/inner")
    assert u == {"templates": [], "pools": ["core/outer"], "reach": ["street_woman"]}
    assert pools.users(lib, "core/unused") == {"templates": [], "pools": [], "reach": []}


def test_samples_use_the_edited_pool(lib_dir):
    lib = lib_of(lib_dir)
    res = pools.samples(lib, "core/light_sky", pools.normalize_model(model("BRAND NEW LIGHT")), seed=3)
    assert res["template"] == "street_woman" and len(res["samples"]) == 3
    assert all(s["text"].startswith("BRAND NEW LIGHT.") for s in res["samples"])
    res = pools.samples(lib, "core/unused", pools.normalize_model(model("only")), seed=1)
    assert res["template"] is None and res["samples"][0]["text"] == "only"
    hidden = pools.samples(lib, "person/body", pools.normalize_model(model("x")), hide=wildcards.is_excluded, seed=1)
    assert hidden["template"] is None  # the NSFW user is hidden: the pool alone


# ------------------------------------------------------------------ saving and the archive


def test_save_keeps_a_backup_and_archives_what_left(lib_dir):
    lib = lib_of(lib_dir)
    path = lib_dir / "core" / "light_sky.txt"
    old = path.read_text(encoding="utf-8")
    m = model(("soft daylight", "2"), "golden hour", desc="light for places that are always outdoors")
    res = pools.save([str(lib_dir)], lib, "core/light_sky", m)  # "low sun" retired, weight 3 -> 2 kept
    assert res["backup"] and res["archived"] == 1 and not res["created"]
    assert (lib_dir / "core" / "light_sky.txt.bak").read_text(encoding="utf-8") == old
    want = "# light for places that are always outdoors\n2::soft daylight\ngolden hour\n"
    assert path.read_text(encoding="utf-8") == want
    arch = lib_dir.parent / "wildcards_archive" / "core" / "light_sky_archive.txt"
    text = arch.read_text(encoding="utf-8")
    assert datetime.date.today().isoformat() in text and text.rstrip().endswith("low sun")
    # an edited text archives the old wording; a second retirement appends
    pools.save([str(lib_dir)], lib_of(lib_dir), "core/light_sky", model(("soft daylight", "2"), "golden hour light"))
    assert arch.read_text(encoding="utf-8").count("# retired from core/light_sky") == 2
    assert arch.read_text(encoding="utf-8").rstrip().endswith("golden hour")
    assert "light_sky_archive" not in lib_of(lib_dir).data  # the archive is never part of the library
    assert not any("archive" in k for k in lib_of(lib_dir).keys())


def test_new_pool_never_overwrites(lib_dir):
    lib = lib_of(lib_dir)
    res = pools.save([str(lib_dir)], lib, "core/light_window", model("window light", desc="soft side light\nindoors"),
                     new=True)
    assert res["created"] and not res["backup"]
    assert (lib_dir / "core" / "light_window.txt").read_text(encoding="utf-8") == \
        "# soft side light\n# indoors\nwindow light\n"
    with pytest.raises(pools.PoolError, match="exists"):
        pools.save([str(lib_dir)], lib_of(lib_dir), "core/light_window", model("other"), new=True)
    assert (lib_dir / "core" / "light_window.txt").read_text(encoding="utf-8").endswith("window light\n")
    pools.save([str(lib_dir)], lib_of(lib_dir), "newfolder/sub/fresh_pool", model("x"), new=True)
    assert (lib_dir / "newfolder" / "sub" / "fresh_pool.txt").exists()
    with pytest.raises(pools.PoolError):
        pools.save([str(lib_dir)], lib_of(lib_dir), "templates/evil", model("x"), new=True)
    with pytest.raises(pools.PoolError):
        pools.save([str(lib_dir)], lib_of(lib_dir), "../../outside", model("x"), new=True)
    assert not (lib_dir.parent.parent / "outside.txt").exists()


def test_retire_only_unused_pools(lib_dir):
    lib = lib_of(lib_dir)
    for used in ("core/light_sky", "core/inner", "core/globbed"):
        with pytest.raises(pools.PoolInUse):
            pools.retire([str(lib_dir)], lib, used)
        assert (lib_dir / (used + ".txt")).exists()
    res = pools.retire([str(lib_dir)], lib, "core/unused")
    assert res["lines"] == 3
    assert not (lib_dir / "core" / "unused.txt").exists() and (lib_dir / "core" / "unused.txt.bak").exists()
    arch = (lib_dir.parent / "wildcards_archive" / "core" / "unused_archive.txt").read_text(encoding="utf-8")
    assert "whole pool core/unused retired" in arch and arch.rstrip().endswith("two") and "# nobody reads me" in arch
    assert "core/unused" not in lib_of(lib_dir).data
    with pytest.raises(pools.PoolError):
        pools.retire([str(lib_dir)], lib_of(lib_dir), "packs/demo/core/x")


# ------------------------------------------------------------------ REST handlers


@pytest.fixture
def store(lib_dir, tmp_path):
    return Store(str(tmp_path / "kdx_console"))


def body(d):
    return json.dumps(d).encode()


def test_api_edit_check_save(store, lib_dir):
    status, d = api.get_pool_edit(store, {"key": "core/light_sky"})
    assert status == 200 and d["file"] == "core/light_sky.txt" and d["archive"].endswith("core/light_sky_archive.txt")
    assert d["pool"]["lines"][0] == {"v": "soft daylight", "w": "3"} and d["users"]["templates"] == ["street_woman"]
    assert api.get_pool_edit(store, {"key": "templates/akt"})[0] == 400
    assert api.get_pool_edit(store, {"key": "../x/y"})[0] == 400
    status, d = api.get_pool_edit(store, {"key": "person/body"})
    assert d["users"]["templates"] == [] and d["users"]["hidden"] == 1  # NSFW switch off
    store.save_config({**store.load_config(), "show_nsfw": True})
    assert api.get_pool_edit(store, {"key": "person/body"})[1]["users"]["templates"] == ["akt"]
    m = {"key": "core/light_sky", "desc": "d", "lines": [{"v": "soft daylight", "w": "3"}, {"v": "noon sun"}]}
    status, d = api.post_pool_check(store, body({**m, "seed": 2}))
    assert status == 200 and d["warnings"] == [] and d["template"] == "street_woman" and len(d["samples"]) == 3
    status, d = api.post_pool_save(store, body(m))
    assert status == 200 and d["archived"] == 1 and d["backup"]
    status, d = api.post_pool_save(store, body({**m, "lines": [{"v": "a teenager"}]}))
    assert status == 400 and "adults only" in d["error"]
    status, d = api.post_pool_check(store, body({**m, "key": "core/light_sky", "new": True}))
    assert status == 400 and "exists" in d["error"]


def test_api_new_and_retire(store, lib_dir):
    status, d = api.post_pool_save(store, body({"key": "core/light_lamp", "new": True, "desc": "lamp light",
                                                "lines": [{"v": "a warm lamp"}]}))
    assert status == 200 and d["created"]
    status, d = api.post_pool_retire(store, body({"key": "core/light_sky"}))
    assert status == 409 and d["in_use"] and d["users"]["templates"] == ["street_woman"]
    status, d = api.post_pool_retire(store, body({"key": "core/light_lamp"}))
    assert status == 200 and d["lines"] == 2
    assert not (lib_dir / "core" / "light_lamp.txt").exists()
