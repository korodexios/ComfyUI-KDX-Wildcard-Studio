"""Overrides grammar and application (per run, config untouched)."""

import pytest
from _helpers import cfg

from kdx_console import engine, overrides
from kdx_console.engine import ConsoleError


def norm(raw):
    return engine.normalize_config(raw)[0]


C = cfg(("portrait", [("portrait", 1), ("selfie", 1, False)]), ("art", [("cubism", 1), ("illustration", 1)]))


def test_parse_full_grammar():
    ov = overrides.parse("art=off, portrait.selfie=on; select=art.cubism\nmode=pin\nseed=12, llm=on, # comment")
    assert ov.toggles == [("art", None, False), ("portrait", "selfie", True)]
    assert ov.select == {"category": "art", "template": "cubism"}
    assert (ov.mode, ov.seed, ov.llm) == ("pin", 12, True)


def test_select_implies_manual():
    assert overrides.parse("select=art.cubism").mode == "manual"


def test_empty_is_noop_and_same_object():
    c = norm(C)
    ov = overrides.parse("  ,, ")
    assert ov.empty
    assert overrides.apply(c, ov) is c


@pytest.mark.parametrize("bad", ["art", "art=maybe", "mode=random", "seed=x", "seed=-1", "select=art"])
def test_parse_errors(bad):
    with pytest.raises(ConsoleError):
        overrides.parse(bad)


def test_apply_does_not_touch_stored_config():
    c = norm(C)
    eff = overrides.apply(c, overrides.parse("art=off, portrait.selfie=on, llm=on"))
    assert c["categories"][1]["enabled"] is True
    assert c["categories"][0]["templates"][1]["enabled"] is False
    assert eff["categories"][1]["enabled"] is False
    assert eff["categories"][0]["templates"][1]["enabled"] is True
    assert eff["llm_enabled"] is True


def test_wildcards_star():
    c = norm(C)
    eff = overrides.apply(c, overrides.parse("*=off, art=on"))
    assert [x["enabled"] for x in eff["categories"]] == [False, True]
    eff = overrides.apply(c, overrides.parse("art.*=off, art.illustration=on"))
    assert [t["enabled"] for t in eff["categories"][1]["templates"]] == [False, True]


def test_enabling_template_enables_its_category():
    raw = cfg(("art", [("cubism", 1)]))
    raw["categories"][0]["enabled"] = False
    eff = overrides.apply(norm(raw), overrides.parse("art.cubism=on"))
    assert eff["categories"][0]["enabled"] is True


def test_unknown_names_list_known_ones():
    c = norm(C)
    with pytest.raises(ConsoleError, match="Known: portrait, art"):
        overrides.apply(c, overrides.parse("nope=off"))
    with pytest.raises(ConsoleError, match="cubism, illustration"):
        overrides.apply(c, overrides.parse("art.nope=on"))


def test_override_drives_sequence():
    c = overrides.apply(norm(C), overrides.parse("portrait=off"))
    p = engine.plan(c, engine.default_state())
    assert (p.category, p.template) == ("art", "cubism")
