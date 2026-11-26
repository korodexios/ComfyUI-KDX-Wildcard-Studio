"""Engine: cursor, repeat, on_end, disabled items, modes, config edits."""

import pytest
from _helpers import SeqSeeds, cfg

from kdx_console import engine
from kdx_console.engine import ConsoleError, Pin


def norm(raw):
    c, _ = engine.normalize_config(raw)
    return c


def run_n(c, n, state=None, seeds=None, **kw):
    """Run n times, return list of (category, template, index) and the final state."""
    seeds = seeds or SeqSeeds()
    state = state or engine.default_state()
    out = []
    for _ in range(n):
        p = engine.plan(c, state, seed_fn=seeds, **kw)
        out.append((p.category, p.template, p.index))
        state = engine.commit(c, state, p, seed_fn=seeds)
    return out, state


def names(seq):
    return [f"{c}.{t}" for c, t, _ in seq]


# ---------------------------------------------------------------- sequential basics

def test_repeat_then_next_template_then_next_category_wraps():
    c = norm(cfg(("a", [("x", 2), ("y", 1)], "next"), ("b", [("z", 1)], "next")))
    seq, _ = run_n(c, 6)
    assert names(seq) == ["a.x", "a.x", "a.y", "b.z", "a.x", "a.x"]
    assert [i for *_, i in seq][:2] == [1, 2]


def test_loop_stays_in_category():
    c = norm(cfg(("a", [("x", 1), ("y", 1)], "loop"), ("b", [("z", 1)])))
    seq, _ = run_n(c, 5)
    assert names(seq) == ["a.x", "a.y", "a.x", "a.y", "a.x"]


def test_stop_blocks_with_message_and_skip_resumes():
    c = norm(cfg(("a", [("x", 1)], "stop"), ("b", [("z", 1)])))
    seq, state = run_n(c, 1)
    assert names(seq) == ["a.x"]
    with pytest.raises(engine.ConsoleFinished, match="on_end = stop"):
        engine.plan(c, state)
    state = engine.skip(c, state)
    assert engine.plan(c, state).template == "z"


def test_reset_starts_from_first_enabled():
    c = norm(cfg(("a", [("x", 1, False), ("y", 3)]), ("b", [("z", 1)])))
    _, state = run_n(c, 2)
    state = engine.reset(state)
    p = engine.plan(c, state)
    assert (p.category, p.template, p.index) == ("a", "y", 1)


def test_repeat_left_and_index():
    c = norm(cfg(("a", [("x", 3)])))
    state = engine.default_state()
    lefts = []
    for _ in range(3):
        p = engine.plan(c, state)
        lefts.append((p.index, p.repeat_left))
        state = engine.commit(c, state, p)
    assert lefts == [(1, 2), (2, 1), (3, 0)]


def test_seed_is_stored_then_renewed():
    seeds = SeqSeeds(7)
    c = norm(cfg(("a", [("x", 5)])))
    state = engine.default_state()
    engine.get_channel(state, seed_fn=seeds)  # next_seed = 7
    p1 = engine.plan(c, state, seed_fn=seeds)
    assert p1.seed == 7
    assert engine.plan(c, state, seed_fn=seeds).seed == 7  # planning is pure
    state = engine.commit(c, state, p1, seed_fn=seeds)
    assert engine.plan(c, state, seed_fn=seeds).seed == 8


# ---------------------------------------------------------------- disabled items

def test_disabled_template_and_category_skipped():
    c = norm(cfg(("a", [("x", 1), ("y", 1, False), ("w", 1)]), ("b", [("z", 1)]), ("c", [("q", 1)])))
    c["categories"][1]["enabled"] = False
    seq, _ = run_n(c, 4)
    assert names(seq) == ["a.x", "a.w", "c.q", "a.x"]


def test_disabled_item_at_cursor_is_skipped():
    c = norm(cfg(("a", [("x", 3), ("y", 1)]), ("b", [("z", 1)])))
    _, state = run_n(c, 1)  # cursor: a.x done=1
    c["categories"][0]["templates"][0]["enabled"] = False
    p = engine.plan(c, state)
    assert (p.template, p.index) == ("y", 1)
    c["categories"][0]["enabled"] = False
    assert engine.plan(c, state).template == "z"


def test_disabled_last_template_in_loop_category_wraps_inside():
    c = norm(cfg(("a", [("x", 1), ("y", 2)], "loop"), ("b", [("z", 1)])))
    _, state = run_n(c, 2)  # cursor a.y done=1
    c["categories"][0]["templates"][1]["enabled"] = False
    assert engine.plan(c, state).template == "x"


def test_nothing_enabled_is_clear_error():
    c = norm(cfg(("a", [("x", 1, False)])))
    with pytest.raises(ConsoleError, match="no template is enabled"):
        engine.plan(c, engine.default_state())
    with pytest.raises(ConsoleError):
        engine.plan(norm({}), engine.default_state())


def test_empty_category_is_skipped():
    c = norm(cfg(("a", []), ("b", [("z", 2)])))
    seq, _ = run_n(c, 3)
    assert names(seq) == ["b.z", "b.z", "b.z"]


# ---------------------------------------------------------------- config edits while running

def test_removed_template_lands_near_old_position():
    c = norm(cfg(("a", [("x", 1), ("y", 5), ("w", 1)])))
    _, state = run_n(c, 2)  # cursor a.y done=1
    c["categories"][0]["templates"].pop(1)
    p = engine.plan(c, state)
    assert (p.template, p.index) == ("w", 1)


def test_removed_category_lands_near_old_index():
    c = norm(cfg(("a", [("x", 1)]), ("b", [("y", 3)]), ("c", [("z", 1)])))
    _, state = run_n(c, 2)  # cursor b.y done=1
    c["categories"].pop(1)
    p = engine.plan(c, state)
    assert (p.category, p.template, p.index) == ("c", "z", 1)


def test_repeat_lowered_below_done_finishes_template():
    c = norm(cfg(("a", [("x", 5), ("y", 1)])))
    _, state = run_n(c, 4)  # done=4
    c["categories"][0]["templates"][0]["repeat"] = 2
    p = engine.plan(c, state)
    assert (p.template, p.index, p.repeat_left) == ("x", 2, 0)
    state = engine.commit(c, state, p)
    assert engine.plan(c, state).template == "y"


def test_removed_last_category_index_clamped():
    c = norm(cfg(("a", [("x", 1)]), ("b", [("y", 3)])))
    _, state = run_n(c, 2)
    c["categories"].pop(1)
    assert engine.plan(c, state).category == "a"


def test_reordered_config_follows_names():
    c = norm(cfg(("a", [("x", 1)]), ("b", [("y", 3)])))
    _, state = run_n(c, 2)  # b.y done=1
    c["categories"].reverse()
    p = engine.plan(c, state)
    assert (p.category, p.template, p.index) == ("b", "y", 2)


# ---------------------------------------------------------------- modes

def test_manual_mode_fixed_template_new_seed_cursor_untouched():
    seeds = SeqSeeds()
    raw = cfg(("a", [("x", 1)]), ("b", [("y", 1), ("z", 1)]), mode="manual", select={"category": "b", "template": "z"})
    c = norm(raw)
    state = engine.default_state()
    engine.get_channel(state, seed_fn=seeds)
    used = []
    for _ in range(3):
        p = engine.plan(c, state, seed_fn=seeds)
        used.append((p.template, p.seed, p.mode))
        state = engine.commit(c, state, p, seed_fn=seeds)
    assert [u[0] for u in used] == ["z", "z", "z"]
    assert len({u[1] for u in used}) == 3
    assert state["channels"]["main"]["category"] is None  # sequential cursor not moved
    assert engine.plan(c, state, mode="sequential").template == "x"


def test_manual_without_select_errors():
    c = norm(cfg(("a", [("x", 1)]), mode="manual"))
    with pytest.raises(ConsoleError, match="select"):
        engine.plan(c, engine.default_state())


def test_pin_mode_reproduces_and_does_not_move():
    c = norm(cfg(("a", [("x", 1)]), ("b", [("y", 2)]), mode="pin", select="b.y", pin_seed=55))
    seq, state = run_n(c, 3)
    assert names(seq) == ["b.y"] * 3
    ps = engine.plan(c, state)
    assert (ps.mode, ps.seed) == ("pin", 55)
    assert state["channels"]["main"]["category"] is None


def test_pin_mode_without_seed_errors():
    c = norm(cfg(("a", [("x", 1)]), mode="pin", select="a.x"))
    with pytest.raises(ConsoleError, match="seed"):
        engine.plan(c, engine.default_state())


def test_pin_object_overrides_everything_even_missing_template():
    c = norm(cfg(("a", [("x", 1)])))
    pin = Pin.parse('{"category":"gone","template":"old_tpl","seed":9,"index":2,"repeat":3,"system_prompt":"p"}')
    p = engine.plan(c, engine.default_state(), pin=pin)
    assert (p.mode, p.template, p.seed, p.index, p.repeat_left, p.system_prompt) == ("pin", "old_tpl", 9, 2, 1, "p")
    assert Pin.parse(pin.to_json()).seed == 9


@pytest.mark.parametrize("bad", ["{", "[]", '{"template":"x"}', '{"seed":1}'])
def test_pin_parse_errors(bad):
    with pytest.raises(ConsoleError):
        Pin.parse(bad)


def test_pin_empty_is_none():
    assert Pin.parse("  ") is None


# ---------------------------------------------------------------- user actions

def test_select_cursor_and_skip():
    c = norm(cfg(("a", [("x", 1)]), ("b", [("y", 3), ("z", 1)])))
    state = engine.select_cursor(c, engine.default_state(), "b", "y")
    assert engine.plan(c, state).template == "y"
    state = engine.skip(c, state)
    assert engine.plan(c, state).template == "z"
    with pytest.raises(ConsoleError):
        engine.select_cursor(c, state, "b", "nope")


def test_skip_through_stop_category_does_not_stop():
    c = norm(cfg(("a", [("x", 3)], "stop"), ("b", [("z", 1)])))
    state = engine.skip(c, engine.default_state())
    assert engine.plan(c, state).template == "z"


# ---------------------------------------------------------------- preview / fingerprint

def test_preview_matches_actual_runs():
    c = norm(cfg(("a", [("x", 2), ("y", 1)]), ("b", [("z", 1)], "stop")))
    seeds = SeqSeeds()
    state = engine.default_state()
    engine.get_channel(state, seed_fn=seeds)
    pv = engine.preview(c, state, count=6)
    actual, _ = run_n(c, 4, state=state, seeds=seeds)
    assert [(u["category"], u["template"], u["index"]) for u in pv["upcoming"]] == actual
    assert pv["upcoming"][0]["seed"] == state["channels"]["main"]["next_seed"]
    assert pv["upcoming"][1]["seed"] is None
    assert "stop" in pv["error"]


def test_fingerprint_changes_every_run_and_is_stable_for_pin():
    c = norm(cfg(("a", [("x", 5)])))
    state = engine.default_state()
    engine.get_channel(state)
    fps = set()
    for _ in range(4):
        fps.add(engine.fingerprint(c, state))
        state = engine.commit(c, state, engine.plan(c, state))
    assert len(fps) == 4
    pin = '{"template":"x","seed":1}'
    assert engine.fingerprint(c, state, pin=pin) == engine.fingerprint(c, engine.default_state(), pin=pin)
    assert engine.fingerprint(c, state, overrides="a=off") != engine.fingerprint(c, state)
    assert "nan" not in engine.fingerprint(c, state).lower()


# ---------------------------------------------------------------- normalization

def test_normalize_config_repairs():
    raw = {
        "mode": "weird",
        "categories": [
            {"name": "Osoba a portrét", "on_end": "bogus", "templates": [
                "__templates/portrait__", {"name": "portrait"}, {"name": "x", "repeat": 0}, {"repeat": 3}]},
            {"key": "Osoba a portrét"},
            "junk",
        ],
    }
    c, warns = engine.normalize_config(raw)
    assert c["mode"] == "sequential"
    cat = c["categories"][0]
    assert cat["key"] == "osoba_a_portret"
    assert cat["on_end"] == "next"
    assert [t["name"] for t in cat["templates"]] == ["portrait", "x"]
    assert cat["templates"][1]["repeat"] == 1
    assert c["categories"][1]["key"] == "osoba_a_portret_2"
    assert len(warns) >= 5


def test_normalize_state_repairs():
    st, warns = engine.normalize_state({"channels": {"main": {"done": "x", "runs": -4, "next_seed": "5"},
                                                     "bad": 3}}, seed_fn=lambda: 1)
    ch = st["channels"]["main"]
    assert (ch["done"], ch["runs"], ch["next_seed"]) == (0, 0, 5)
    assert "bad" not in st["channels"]
    assert warns
