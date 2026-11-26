"""Wildcard packs: export, the checks, unsafe zips, install into packs/<pack>/, uninstall, REST."""

import io
import json
import os
import zipfile

import _helpers  # noqa: F401
import pytest

from kdx_console import api, packs, wildcards
from kdx_console.store import Store
from kdx_console.wildcard_engine import Library

POOLS = {
    "core/shot": "a close portrait, 4:5\n2::a wide view, 3:2",
    "core/light": "soft daylight\nlow sun",
    "core/light_lamp": "a warm lamp",
    "person/age": "early 20s\n30s",
    "person/hair": "{long|short} __person/hair_color__ hair",
    "person/hair_color": "dark\nred",
    "place/room": "a kitchen",
    "unused/thing": "never reached",
}
PORTRAIT = "A portrait of a woman in her __person/age__ with __person/hair__, __light__, in {__place/room__}. " \
           "This is __core/shot__."


def _files(root, mapping):
    for key, text in mapping.items():
        p = root / (key + ".txt")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text + "\n", encoding="utf-8")


@pytest.fixture
def wc(tmp_path):
    root = tmp_path / "wc"
    _files(root, POOLS)
    _files(root, {"templates/portrait": PORTRAIT, "templates/simple": "A room: __place/room__. Shot __core/shot__.",
                  "templates/akt_art": "A study, __core/light__. __core/shot__."})
    return root


def lib_of(root):
    return Library.from_dirs([str(root)])


def export(root, names=("portrait",), **meta):
    return packs.export(lib_of(root), list(names), {"name": "street", "author": "tester", **meta}, samples_n=20)


def zip_of(entries: dict, *, attrs: dict | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries.items():
            info = zipfile.ZipInfo(name)
            if attrs and name in attrs:
                info.external_attr = attrs[name] << 16
            zf.writestr(info, data if isinstance(data, bytes) else data.encode("utf-8"))
    return buf.getvalue()


def good_zip(root, **kw) -> bytes:
    res = export(root, **kw)
    assert res["zip"], res["errors"]
    return res["zip"]


def repack(data: bytes, change) -> bytes:
    """Unzip, let ``change(files: dict)`` edit, zip again (pack.json is kept as it was unless changed)."""
    zf = zipfile.ZipFile(io.BytesIO(data))
    files = {n: zf.read(n).decode("utf-8") for n in zf.namelist()}
    change(files)
    return zip_of(files)


# ------------------------------------------------------------------ engine: packs are a namespace


def test_glob_and_short_names_never_reach_into_packs():
    lib = Library.from_mapping({"core/light": "mine", "packs/p/core/light": "theirs", "packs/p/x/light": "theirs too"})
    assert lib.match_keys("light") == ["core/light"]
    assert lib.match_keys("*/light") == ["core/light"]
    assert lib.match_keys("core") == ["core/light"]
    assert lib.expand("__light__", 1).text == "mine"


def test_short_names_and_globs_inside_a_pack_stay_inside():
    lib = Library.from_mapping({"core/light": "mine", "packs/p/core/light": "a", "packs/p/x/light": "b",
                                "packs/q/core/light": "other pack"})
    assert lib.match_keys("packs/p/light") == ["packs/p/core/light", "packs/p/x/light"]
    assert lib.match_keys("packs/p/*/light") == ["packs/p/core/light", "packs/p/x/light"]
    assert lib.match_keys("packs/p/core") == ["packs/p/core/light"]
    assert lib.match_keys("packs/p/core/light") == ["packs/p/core/light"]


# ------------------------------------------------------------------ export


def test_export_collects_every_reached_pool(wc):
    res = export(wc)
    assert res["errors"] == []
    assert res["files"] == ["core/light.txt", "core/shot.txt", "person/age.txt",
                            "person/hair.txt", "person/hair_color.txt", "place/room.txt", "templates/portrait.txt"]
    meta = res["meta"]
    assert meta["templates"] == ["portrait"] and meta["nsfw"] is False and meta["license"] == packs.DEFAULT_LICENSE == "CC0-1.0"
    zf = zipfile.ZipFile(io.BytesIO(res["zip"]))
    assert zf.namelist()[0] == "pack.json"
    pj = json.loads(zf.read("pack.json"))
    assert pj["files"]["core/shot.txt"] == packs.md5(zf.read("core/shot.txt").decode())
    # the short token __light__ is kept (it reads core/light, not core/light_lamp, as in the library)
    assert any(w["code"] == "full_token" for w in res["warnings"])


def test_export_is_deterministic_and_copies_files_verbatim(wc):
    (wc / "person" / "age.txt").write_text("# who\n3::early 20s\n30s\n", encoding="utf-8")
    a, b = export(wc)["zip"], export(wc)["zip"]
    assert a == b
    assert zipfile.ZipFile(io.BytesIO(a)).read("person/age.txt").decode() == "# who\n3::early 20s\n30s\n"


def test_export_nsfw_name_marks_the_pack(wc):
    assert export(wc, ["akt_art"])["meta"]["nsfw"] is True
    assert export(wc, ["simple"], nsfw=True)["meta"]["nsfw"] is True


def test_export_flattens_template_sub_folders(tmp_path):
    root = tmp_path / "wc"
    _files(root, {"core/x": "a", "templates/people/portrait": "A __core/x__ and __templates/people/inner__.",
                  "templates/people/inner": "B."})
    res = packs.export(lib_of(root), ["people/portrait"], {"name": "pp", "author": "t"}, samples_n=5)
    assert "templates/people_portrait.txt" in res["files"] and "templates/people_inner.txt" in res["files"]
    text = zipfile.ZipFile(io.BytesIO(res["zip"])).read("templates/people_portrait.txt").decode()
    assert "__templates/people_inner__" in text


def test_export_refuses_templates_of_installed_packs(wc):
    _files(wc, {"packs/other/core/x": "y", "templates/mixed": "A __packs/other/core/x__ thing, 1:1."})
    with pytest.raises(packs.PackError, match="installed pack"):
        export(wc, ["mixed"])


def test_export_unknown_template_and_empty_pick(wc):
    with pytest.raises(packs.PackError, match="no template"):
        export(wc, ["nope"])
    with pytest.raises(packs.PackError, match="at least one"):
        export(wc, [])


def test_export_needs_name_and_author(wc):
    res = packs.export(lib_of(wc), ["simple"], {"name": "Bad Name!"}, samples_n=5)
    assert res["zip"] is None
    codes = {e["code"] for e in res["errors"]}
    assert "name" in codes and "manifest" in codes  # invalid name, author missing


# ------------------------------------------------------------------ unsafe zips


@pytest.mark.parametrize("name", ["../evil.txt", "a/../../evil.txt", "/etc/evil.txt", "C:/evil.txt", "a\\..\\evil.txt",
                                  "./x.txt", "a//b.txt"])
def test_path_traversal_is_refused(name):
    with pytest.raises(packs.PackError, match="unsafe zip"):
        packs.read_zip(zip_of({"pack.json": "{}", name: "x"}))


@pytest.mark.parametrize("name", ["run.py", "core/x.exe", "image.png", "core/x.TXT", "README.md", "templates/x.txt.sh"])
def test_only_txt_and_pack_json(name):
    with pytest.raises(packs.PackError, match="only .txt files and pack.json"):
        packs.read_zip(zip_of({"pack.json": "{}", name: "x"}))


def test_symlink_is_refused():
    data = zip_of({"pack.json": "{}", "core/link.txt": "/etc/passwd"}, attrs={"core/link.txt": 0o120777})
    with pytest.raises(packs.PackError, match="symbolic links"):
        packs.read_zip(data)


def test_huge_file_is_refused(monkeypatch):
    monkeypatch.setattr(packs, "MAX_FILE_BYTES", 1000)
    with pytest.raises(packs.PackError, match="larger than"):
        packs.read_zip(zip_of({"pack.json": "{}", "core/big.txt": "a\n" * 2000}))


def test_zip_bomb_total_is_refused(monkeypatch):
    monkeypatch.setattr(packs, "MAX_TOTAL_BYTES", 5000)
    entries = {"pack.json": "{}", **{f"core/f{i}.txt": "x" * 900 for i in range(10)}}
    with pytest.raises(packs.PackError, match="add up to more than"):
        packs.read_zip(zip_of(entries))


def test_too_large_upload_and_too_many_files(monkeypatch):
    with pytest.raises(packs.PackError, match="larger than"):
        packs.read_zip(b"x" * (packs.MAX_ZIP_BYTES + 1))
    monkeypatch.setattr(packs, "MAX_FILES", 3)
    with pytest.raises(packs.PackError, match="more than 3 files"):
        packs.read_zip(zip_of({"pack.json": "{}", **{f"core/f{i}.txt": "x" for i in range(5)}}))


def test_not_a_zip_not_utf8_no_manifest_encrypted():
    with pytest.raises(packs.PackError, match="not a zip"):
        packs.read_zip(b"PK not really a zip")
    with pytest.raises(packs.PackError, match="no file"):
        packs.read_zip(b"")
    with pytest.raises(packs.PackError, match="not UTF-8"):
        packs.read_zip(zip_of({"pack.json": "{}", "core/x.txt": b"\xff\xfe\x00bad"}))
    with pytest.raises(packs.PackError, match="pack.json is missing"):
        packs.read_zip(zip_of({"core/x.txt": "a"}))
    raw = bytearray(zip_of({"core/x.txt": "a", "pack.json": "{}"}))
    for sig, off in ((bytes([80, 75, 3, 4]), 6), (bytes([80, 75, 1, 2]), 8)):  # "encrypted" flag, first file
        i = raw.find(sig)
        raw[i + off] |= 0x1
    with pytest.raises(packs.PackError, match="encrypted"):
        packs.read_zip(bytes(raw))


def test_nested_manifest_and_duplicates_are_refused():
    with pytest.raises(packs.PackError, match="outside the pack folder"):
        packs.read_zip(zip_of({"pack.json": "{}", "core/pack.json": "{}"}))
    with pytest.raises(packs.PackError, match="twice"):
        packs.read_zip(zip_of({"pack.json": "{}", "core/x.txt": "a", "CORE/X.txt": "b"}))


def test_one_top_folder_is_accepted(wc):
    data = good_zip(wc)
    zf = zipfile.ZipFile(io.BytesIO(data))
    wrapped = zip_of({f"street/{n}": zf.read(n) for n in zf.namelist()})
    manifest, files = packs.read_zip(wrapped)
    assert json.loads(manifest)["name"] == "street" and "templates/portrait.txt" in files


# ------------------------------------------------------------------ checks (lint + struct)


def inspect(root, data):
    return packs.inspect(data, lib_of(root), lambda n: packs.read_installed(str(root), n), samples_n=20)


def codes(res):
    return {e["code"] for e in res["errors"]}


def test_inspect_good_pack(wc):
    res = inspect(wc, good_zip(wc))
    assert res["can_install"] and res["errors"] == []
    assert len(res["samples"]) == 3 and all(s["text"].startswith("A portrait") for s in res["samples"])
    assert [t["installed_as"] for t in res["templates"]] == ["street_portrait"]
    assert res["templates"][0]["exists"] is True  # the user has a template "portrait" too (it stays)
    st = {p["key"]: p["status"] for p in res["pools"]}
    assert st["core/shot"] == "same"


def test_inspect_reports_differing_pools(wc):
    data = good_zip(wc)
    (wc / "core" / "shot.txt").write_text("my own shot, 1:1\n", encoding="utf-8")
    st = {p["key"]: p["status"] for p in inspect(wc, data)["pools"]}
    assert st["core/shot"] == "differs" and st["core/light"] == "same"


def test_changed_file_fails_md5_and_unlisted_file(wc):
    def edit(f):
        f["core/light.txt"] = "changed\n"
        f["core/extra.txt"] = "x\n"
    res = inspect(wc, repack(good_zip(wc), edit))
    assert {"md5", "unlisted"} <= codes(res) and not res["can_install"]


def _with(wc, path, text):
    """A good pack with one file replaced, pack.json updated to match (so only the text rules decide)."""
    def edit(f):
        f[path] = text
        meta = json.loads(f["pack.json"])
        meta["files"][path] = packs.md5(packs._text(text))
        meta["templates"] = sorted(p[10:-4] for p in f if p.startswith("templates/"))
        f["pack.json"] = json.dumps(meta)
    return repack(good_zip(wc), edit)


@pytest.mark.parametrize("text,code", [
    ("a girl with __core/light__, 4:5", "minor"),
    ("a woman, 16 years old, 4:5", "minor"),
    ("a woman aged 15, 4:5", "minor"),
    ("a teenage model, 4:5", "minor"),
    ("A __core/nope__ thing, 4:5", "missing"),
    ("A __packs/other/core/x__ thing, 4:5", "outside"),
    ("A {broken thing, 4:5", "braces"),
    ("3::2::A thing, 4:5", "weight"),
    ("A bell\x07 rings, 4:5", "control"),
])
def test_text_rules(wc, text, code):
    res = inspect(wc, _with(wc, "templates/portrait.txt", text))
    assert code in codes(res), res["errors"]
    assert not res["can_install"]


def test_adults_in_their_twenties_pass(wc):
    res = inspect(wc, _with(wc, "templates/portrait.txt", "A woman in her early 20s, 25 years old, __core/shot__."))
    assert "minor" not in codes(res)


def test_nsfw_template_in_sfw_pack(wc):
    res = inspect(wc, _with(wc, "templates/akt_x.txt", "A study, __core/shot__."))
    assert "nsfw" in codes(res)


@pytest.mark.parametrize("path", ["Core/x.txt", "core/my file.txt", "packs/p/x.txt", "templates/sub/x.txt",
                                  "a/b/c/d/e/f/g.txt", "templates/Big.txt"])
def test_bad_paths(wc, path):
    assert "path" in codes(inspect(wc, _with(wc, path, "x")))


def test_struct_warnings_do_not_block(wc):
    res = inspect(wc, _with(wc, "templates/portrait.txt", "a lower case start  with __core/light__"))
    warn = {w["code"] for w in res["warnings"]}
    assert {"ratio", "lowercase", "spaces"} <= warn and res["can_install"]


def test_manifest_rules(wc):
    def edit(f):
        meta = json.loads(f["pack.json"])
        meta.update(format=2, version="one", nsfw="no", license="Proprietary")
        f["pack.json"] = json.dumps(meta)
    res = inspect(wc, repack(good_zip(wc), edit))
    assert {"format", "version", "nsfw"} <= codes(res)
    assert any(w["code"] == "license" for w in res["warnings"])
    bad = repack(good_zip(wc), lambda f: f.update({"pack.json": "[1, 2]"}))
    assert "manifest" in codes(inspect(wc, bad))


# ------------------------------------------------------------------ install / uninstall


def test_install_into_namespace_and_rewrite_tokens(wc):
    data = good_zip(wc)
    # the user's library changes after the export: install must not touch it
    (wc / "core" / "shot.txt").write_text("my own shot, 1:1\n", encoding="utf-8")
    before = {p: p.read_bytes() for p in wc.rglob("*.txt")}
    res = inspect(wc, data)
    done = packs.install(str(wc), res["_meta"], res["_files"], lib_of(wc))
    assert done["templates"] == {"portrait": "street_portrait"} and done["pools"] == 6
    assert all(p.read_bytes() == b for p, b in before.items())  # nothing existing changed
    tpl = (wc / "templates" / "street_portrait.txt").read_text(encoding="utf-8")
    assert "__packs/street/person/age__" in tpl and "__packs/street/light__" in tpl
    assert (wc / "packs" / "street" / "person" / "hair.txt").read_text().strip() == \
        "{long|short} __packs/street/person/hair_color__ hair"
    lib = lib_of(wc)
    standalone = packs.pack_library(res["_files"])
    for seed in range(30):  # same prompt as the pack on its own
        assert lib.expand("__templates/street_portrait__", seed).text == \
            standalone.expand("__templates/portrait__", seed).text
    assert lib.expand("__core/shot__", 1).text == "my own shot, 1:1"  # the user's pool is untouched
    assert "packs/street/core/light" not in lib.match_keys("light")  # the user's short tokens stay theirs
    rec = packs.list_installed([str(wc)])
    assert [(p["name"], p["templates"], p["nsfw"]) for p in rec] == [("street", ["street_portrait"], False)]


def test_install_twice_needs_replace_and_keeps_edits(wc):
    res = inspect(wc, good_zip(wc))
    packs.install(str(wc), res["_meta"], res["_files"], lib_of(wc))
    with pytest.raises(packs.PackExists):
        packs.install(str(wc), res["_meta"], res["_files"], lib_of(wc))
    tpl = wc / "templates" / "street_portrait.txt"
    tpl.write_text("my edit, 1:1\n", encoding="utf-8")
    res2 = inspect(wc, good_zip(wc, version="1.1.0"))
    assert res2["installed"] == "1.0.0" and res2["templates"][0]["installed_as"] == "street_portrait"
    done = packs.install(str(wc), res2["_meta"], res2["_files"], lib_of(wc), replace=True)
    assert done["replaced"] and (wc / "templates" / "street_portrait.txt.bak").read_text() == "my edit, 1:1\n"
    assert packs.list_installed([str(wc)])[0]["version"] == "1.1.0"
    assert not [p for p in (wc / "packs").iterdir() if p.name.startswith(".")]  # no staging folder left


def test_template_name_collision_gets_a_suffix(wc):
    _files(wc, {"templates/street_portrait": "Mine, 1:1."})
    res = inspect(wc, good_zip(wc))
    assert res["templates"][0]["installed_as"] == "street_portrait_2"
    packs.install(str(wc), res["_meta"], res["_files"], lib_of(wc))
    assert (wc / "templates" / "street_portrait.txt").read_text() == "Mine, 1:1.\n"


def test_nsfw_pack_templates_are_hidden_by_name(wc):
    res = inspect(wc, good_zip(wc, names=["simple"], nsfw=True))
    assert res["templates"][0]["installed_as"] == "nsfw_street_simple"
    assert wildcards.is_excluded("nsfw_street_simple")


def test_uninstall_removes_the_pack_and_keeps_edited_templates(wc):
    res = inspect(wc, good_zip(wc, names=["portrait", "simple"]))
    packs.install(str(wc), res["_meta"], res["_files"], lib_of(wc))
    (wc / "templates" / "street_simple.txt").write_text("edited, 1:1\n", encoding="utf-8")
    out = packs.uninstall(str(wc), "street")
    assert out == {"name": "street", "removed": ["street_portrait"], "kept": ["street_simple"]}
    assert not (wc / "packs" / "street").exists() and (wc / "templates" / "street_simple.txt").exists()
    assert (wc / "templates" / "portrait.txt").exists()  # the user's own template
    with pytest.raises(packs.PackError, match="not installed"):
        packs.uninstall(str(wc), "street")
    with pytest.raises(packs.PackError, match="invalid"):
        packs.uninstall(str(wc), "../templates")


def test_install_refuses_a_link_target(wc, tmp_path):
    res = inspect(wc, good_zip(wc))
    (wc / "packs").mkdir()
    try:
        os.symlink(str(tmp_path), str(wc / "packs" / "street"), target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("no symlinks here")
    with pytest.raises(packs.PackError):
        packs.install(str(wc), res["_meta"], res["_files"], lib_of(wc), replace=True)


# ------------------------------------------------------------------ REST


@pytest.fixture
def env(wc, tmp_path, monkeypatch):
    monkeypatch.delenv(wildcards.ENV_DIRS, raising=False)
    monkeypatch.setattr(wildcards, "_dirs_provider", lambda: [str(wc)])
    monkeypatch.setattr(packs, "SAMPLES", 20)
    store = Store(str(tmp_path / "kdx_console"))
    store.save_config({"categories": [{"key": "mine", "name": "Mine", "templates": []}]})
    return store, wc


def body(d):
    return json.dumps(d).encode()


def test_api_export_plan_and_zip(env):
    store, wc = env
    st, d = api.post_pack_plan(store, body({"templates": ["portrait"], "meta": {"name": "street", "author": "t"}}))
    assert st == 200 and d["ok"] and "zip" not in d and "core/shot.txt" in d["files"]
    st, d = api.post_pack_export(store, body({"templates": ["portrait"], "meta": {"name": "street", "author": "t"}}))
    assert st == 200 and d["filename"] == "street-1.0.0.zip" and d["_zip"][:2] == b"PK"
    st, d = api.post_pack_export(store, body({"templates": ["portrait"], "meta": {"name": "x"}}))
    assert st == 400 and d["errors"]
    st, d = api.post_pack_export(store, body({"templates": ["akt_art"], "meta": {"name": "x", "author": "t"}}))
    assert st == 400 and "NSFW" in d["error"]


def test_api_inspect_install_uninstall(env):
    store, wc = env
    data = api.post_pack_export(store, body({"templates": ["portrait", "simple"],
                                             "meta": {"name": "street", "author": "t"}}))[1]["_zip"]
    st, d = api.post_pack_inspect(store, data)
    assert st == 200 and d["can_install"] and "_files" not in d and len(d["samples"]) == 3
    st, d = api.post_pack_install(store, data, {"new_category": "Street pack"})
    assert st == 200 and d["category"] == "street_pack"
    cfg = store.load_config()
    cat = next(c for c in cfg["categories"] if c["key"] == "street_pack")
    assert [t["name"] for t in cat["templates"]] == ["street_portrait", "street_simple"]
    assert "street_portrait" in wildcards.list_templates()
    st, d = api.post_pack_install(store, data, {})
    assert st == 409 and d["exists"]
    st, d = api.post_pack_install(store, data, {"replace": "1", "category": "mine"})
    assert st == 200 and d["installed"]["replaced"]
    st, d = api.get_packs(store)
    assert [p["name"] for p in d["packs"]] == ["street"] and "root" not in d["packs"][0]
    st, d = api.post_pack_uninstall(store, body({"name": "street"}))
    assert st == 200 and d["removed"] == ["street_portrait", "street_simple"]
    cfg = store.load_config()
    assert all(not c["templates"] for c in cfg["categories"])
    assert api.post_pack_uninstall(store, body({"name": "street"}))[0] == 400


def test_api_install_refuses_bad_zip_and_unknown_category(env):
    store, wc = env
    st, d = api.post_pack_install(store, zip_of({"pack.json": "{}", "../x.txt": "a"}), {})
    assert st == 400 and "unsafe" in d["error"]
    assert not (wc / "packs").exists()
    st, d = api.post_pack_install(store, b"PK", {"category": "nope"})
    assert st == 400 and "category" in d["error"]


def test_api_nsfw_packs_follow_the_switch(env):
    store, wc = env
    store.save_config({**store.load_config(), "show_nsfw": True})
    data = api.post_pack_export(store, body({"templates": ["akt_art"], "meta": {"name": "art", "author": "t"}}))[1]
    assert data["ok"], data
    zipped = data["_zip"]
    store.save_config({**store.load_config(), "show_nsfw": False})
    st, d = api.post_pack_inspect(store, zipped)
    assert d["errors"][0]["code"] == "nsfw_hidden" and d["samples"] == [] and not d["can_install"]
    assert api.post_pack_install(store, zipped, {})[0] == 400
    store.save_config({**store.load_config(), "show_nsfw": True})
    assert api.post_pack_install(store, zipped, {})[0] == 200
    store.save_config({**store.load_config(), "show_nsfw": False})
    st, d = api.get_packs(store)
    assert d["packs"] == [] and d["hidden"] == 1
    assert api.post_pack_uninstall(store, body({"name": "art"}))[0] == 400
