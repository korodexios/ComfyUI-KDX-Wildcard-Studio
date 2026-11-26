"""The data folder: <user dir>/kdx_wildcard_studio, moved once from the old <user dir>/kdx_console."""

import json
import os

import _helpers  # noqa: F401

from kdx_console import store


def test_old_folder_is_moved_and_config_paths_follow(tmp_path):
    old = tmp_path / "kdx_console"
    (old / "wildcards").mkdir(parents=True)
    (old / "wildcards" / "a.txt").write_text("x\n", encoding="utf-8")
    other = str(tmp_path / "elsewhere")
    cfg = {"schema_version": 1, "wildcard_dirs": [str(old / "wildcards"), other], "categories": []}
    (old / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    root = store.migrate_root(str(tmp_path))
    new = tmp_path / "kdx_wildcard_studio"
    assert root == str(new) and not old.exists()
    assert (new / "wildcards" / "a.txt").read_text(encoding="utf-8") == "x\n"
    dirs = json.loads((new / "config.json").read_text(encoding="utf-8"))["wildcard_dirs"]
    assert dirs == [str(new / "wildcards"), other]


def test_fresh_install_and_existing_new_folder(tmp_path):
    assert store.migrate_root(str(tmp_path)) == str(tmp_path / "kdx_wildcard_studio")
    assert not (tmp_path / "kdx_wildcard_studio").exists()  # created later by the first write, not here
    (tmp_path / "kdx_console").mkdir()
    (tmp_path / "kdx_wildcard_studio").mkdir()
    assert store.migrate_root(str(tmp_path)) == str(tmp_path / "kdx_wildcard_studio")
    assert (tmp_path / "kdx_console").is_dir()  # both exist: the old one is left alone


def test_config_without_old_paths_is_not_rewritten(tmp_path):
    old = tmp_path / "kdx_console"
    old.mkdir()
    (old / "config.json").write_text('{"wildcard_dirs": []}', encoding="utf-8")
    before = os.path.getmtime(old / "config.json")
    store.migrate_root(str(tmp_path))
    new = tmp_path / "kdx_wildcard_studio" / "config.json"
    assert new.read_text(encoding="utf-8") == '{"wildcard_dirs": []}' and os.path.getmtime(new) == before
