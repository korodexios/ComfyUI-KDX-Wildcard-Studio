"""kdx_console/wildcards.py — folders (config > env > auto), template list, errors. No Impact Pack."""

import os

import _helpers  # noqa: F401
import pytest

from kdx_console import engine, wildcards
from kdx_console.engine import ConsoleError


def write(root, rel, text):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)


@pytest.fixture
def lib_dir(tmp_path, monkeypatch):
    write(tmp_path, "templates/portrait.txt", "a __person/age__ woman, {soft|hard} light\n")
    write(tmp_path, "templates/art/cubism.txt", "cubist __person/age__ figure\n")
    write(tmp_path, "templates/nsfw_x.txt", "excluded\n")
    write(tmp_path, "person/age.txt", "30s\n40s\n")
    monkeypatch.delenv(wildcards.ENV_DIRS, raising=False)
    monkeypatch.setattr(wildcards, "_dirs_provider", lambda: [str(tmp_path)])
    return tmp_path


def test_no_impact_import():
    import sys
    assert not any(m.startswith("impact") for m in sys.modules)
    src = open(wildcards.__file__, encoding="utf-8").read()
    assert "import impact" not in src and "/impact/" not in src


def test_expand_template_token(lib_dir):
    out = wildcards.expand(engine.template_token("portrait"), 5)
    assert out.startswith("a ") and ("30s" in out or "40s" in out) and "__" not in out
    assert out == wildcards.expand(engine.template_token("portrait"), 5)


def test_list_templates_filters_and_nests(lib_dir):
    assert wildcards.list_templates() == ["art/cubism", "portrait"]


def test_source_priority(tmp_path, monkeypatch):
    monkeypatch.setattr(wildcards, "_dirs_provider", lambda: [])
    monkeypatch.setenv(wildcards.ENV_DIRS, os.pathsep.join([str(tmp_path / "a"), str(tmp_path / "b")]))
    assert wildcards.resolve_dirs() == ([str(tmp_path / "a"), str(tmp_path / "b")], "env")
    assert wildcards.resolve_dirs(["/x"]) == (["/x"], "config")
    monkeypatch.delenv(wildcards.ENV_DIRS)
    dirs, src = wildcards.resolve_dirs()
    assert src == "auto" and all(os.path.isdir(d) for d in dirs)


def test_user_folder_wins_automatic_when_it_has_files(tmp_path, monkeypatch):
    monkeypatch.setattr(wildcards, "_dirs_provider", lambda: [])
    monkeypatch.delenv(wildcards.ENV_DIRS, raising=False)
    monkeypatch.setattr(wildcards, "_user_root_provider", lambda: str(tmp_path / "kdx_console"))
    user = tmp_path / "kdx_console" / "wildcards"
    os.makedirs(user)
    assert wildcards.resolve_dirs()[0] != [str(user)]  # empty folder: fall back
    write(user, "README.md", "not a wildcard")
    assert wildcards.resolve_dirs()[0] != [str(user)]
    write(user, "templates/x.txt", "hello\n")
    assert wildcards.resolve_dirs() == ([str(user)], "auto")
    assert wildcards.list_templates() == ["x"]
    assert wildcards.info()["user_dir"] == str(user)


def test_broken_provider_falls_back(monkeypatch):
    def boom():
        raise RuntimeError("config gone")
    monkeypatch.setattr(wildcards, "_dirs_provider", boom)
    monkeypatch.delenv(wildcards.ENV_DIRS, raising=False)
    assert wildcards.resolve_dirs()[1] == "auto"


def test_empty_library_is_a_clear_error(tmp_path, monkeypatch):
    monkeypatch.setattr(wildcards, "_dirs_provider", lambda: [str(tmp_path / "nothing")])
    with pytest.raises(ConsoleError, match="no wildcard files found"):
        wildcards.expand("__templates/x__", 1)


def test_info(lib_dir):
    wildcards.expand("__nope__ " + engine.template_token("portrait"), 1)
    i = wildcards.info([str(lib_dir), str(lib_dir / "missing")])
    assert i["source"] == "config" and i["files"] == 4 and i["templates"] == 2
    assert i["missing_dirs"] == [str(lib_dir / "missing")]
    assert i["last_missing"] == ["nope"]


def test_config_keeps_wildcard_dirs():
    c, w = engine.normalize_config({"wildcard_dirs": [" /a ", "/a", "", 5, "/b"]})
    assert c["wildcard_dirs"] == ["/a", "/b"] and not w
    c, w = engine.normalize_config({"wildcard_dirs": "/only"})
    assert c["wildcard_dirs"] == ["/only"]
    c, w = engine.normalize_config({"wildcard_dirs": {"x": 1}})
    assert c["wildcard_dirs"] == [] and w
    assert engine.normalize_config({})[0]["wildcard_dirs"] == []
