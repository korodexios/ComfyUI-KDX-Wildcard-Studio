"""Templates removed in the panel (``ignored``) are kept out of Import until restored."""

from kdx_console import engine, importer


def _cfg(**kw):
    raw = {"categories": [{"key": "art", "name": "art", "templates": [{"name": "art/a"}]}]}
    raw.update(kw)
    return engine.normalize_config(raw)[0]


def test_ignored_is_normalized():
    c, w = engine.normalize_config({"ignored": ["templates/x", "x", " y ", 5, "", None]})
    assert c["ignored"] == ["x", "y"] and not w
    assert engine.normalize_config({})[0]["ignored"] == []
    assert engine.normalize_config({"ignored": "bad"})[0]["ignored"] == []


def test_import_skips_ignored():
    cfg = _cfg(ignored=["art/b"])
    new, report = importer.merge(cfg, ["art/a", "art/b", "art/c"])
    names = [t["name"] for t in new["categories"][0]["templates"]]
    assert names == ["art/a", "art/c"]
    assert report["added"] == ["art.art/c"]


def test_import_after_restore_brings_them_back():
    cfg = _cfg(ignored=["art/b"])
    new, _ = importer.merge({**cfg, "ignored": []}, ["art/a", "art/b"])
    assert [t["name"] for t in new["categories"][0]["templates"]] == ["art/a", "art/b"]


def test_empty_category_survives_normalize():
    c, _ = engine.normalize_config({"categories": [{"name": "Nová kategória"}]})
    assert c["categories"][0]["key"] == "nova_kategoria" and c["categories"][0]["templates"] == []
