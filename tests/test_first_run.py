"""First start: bundled starter wildcards are installed and imported, existing libraries are left alone."""

import os
import re

import _helpers  # noqa: F401
import pytest

from kdx_console import api, engine, wildcards
from kdx_console.store import Store
from kdx_console.wildcard_engine import Library


@pytest.fixture
def fresh(tmp_path, monkeypatch):
    store = Store(root=str(tmp_path / "kdx_console"))
    monkeypatch.delenv(wildcards.ENV_DIRS, raising=False)
    monkeypatch.setattr(wildcards, "_dirs_provider", lambda: store.load_config().get("wildcard_dirs") or [])
    monkeypatch.setattr(wildcards, "_user_root_provider", lambda: store.root)
    monkeypatch.setattr(wildcards, "automatic_dirs", _only_user(wildcards.automatic_dirs, store))
    return store


def _only_user(orig, store):
    """Automatic folders without the real Impact/ComfyUI folders of the test machine."""
    def auto():
        user = os.path.join(store.root, wildcards.USER_SUBDIR)
        return [user] if os.path.isdir(user) and wildcards._has_txt(user) else []
    return auto


def test_starter_library_is_complete_and_safe():
    lib = Library.from_dirs([wildcards.STARTER_DIR])
    tpls = wildcards.filter_templates(lib.keys())
    assert len(tpls) >= 4
    for t in tpls:
        for seed in range(60):
            r = lib.expand(engine.template_token(t), seed)
            assert not r.missing, (t, r.missing)
            assert not re.search(r"__|[{}|]", r.text), (t, r.text)
    text = " ".join(e.value for v in lib.data.values() for e in v).lower()
    assert not re.search(r"\b(nude|naked|nsfw|topless|lingerie)\b", text)


def test_fresh_install_gets_starter_and_categories(fresh):
    done = api.first_run_setup(fresh)
    user = os.path.join(fresh.root, "wildcards")
    assert done["starter"] == user and done["imported"] >= 4
    cats = fresh.load_config()["categories"]
    assert {c["key"] for c in cats} == {"people", "places", "things"}
    # works right away
    assert wildcards.expand(engine.template_token(cats[0]["templates"][0]["name"]), 1)


def test_second_start_changes_nothing(fresh):
    api.first_run_setup(fresh)
    cfg = fresh.load_config()
    cfg["categories"][0]["enabled"] = False
    fresh.save_config(cfg)
    assert api.first_run_setup(fresh) == {"starter": None, "imported": 0}
    assert fresh.load_config()["categories"][0]["enabled"] is False


def test_existing_library_is_not_overwritten(fresh):
    user = os.path.join(fresh.root, "wildcards", "templates")
    os.makedirs(user)
    with open(os.path.join(user, "mine.txt"), "w", encoding="utf-8") as f:
        f.write("my own prompt\n")
    done = api.first_run_setup(fresh)
    assert done["starter"] is None and done["imported"] == 1
    assert not os.path.exists(os.path.join(fresh.root, "wildcards", "core"))


def test_user_chosen_folders_skip_the_starter(fresh, tmp_path):
    cfg = fresh.load_config()
    cfg["wildcard_dirs"] = [str(tmp_path / "elsewhere")]
    fresh.save_config(cfg)
    assert api.first_run_setup(fresh)["starter"] is None
