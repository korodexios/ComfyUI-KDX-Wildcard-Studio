"""Store: persistence, atomic writes, corruption, concurrency, run/commit semantics."""

import json
import os
import threading

import pytest
from _helpers import SeqSeeds, cfg, fake_expand

from kdx_console.engine import ConsoleError
from kdx_console.store import Store


@pytest.fixture
def store(tmp_path):
    s = Store(str(tmp_path / "kdx_console"), seed_fn=SeqSeeds())
    s.save_config(cfg(("a", [("x", 2), ("y", 1)]), ("b", [("z", 1)])))
    return s


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def test_run_persists_and_survives_restart(store):
    r1 = store.run(fake_expand)
    assert r1.prompt.startswith("T:x#")
    assert (r1.plan.index, r1.plan.repeat_left) == (1, 1)
    store.run(fake_expand)
    restarted = Store(store.root, seed_fn=SeqSeeds(5000))
    r3 = restarted.run(fake_expand)
    assert r3.plan.template == "y"
    data = json.loads(read(restarted.state_path))
    assert data["schema_version"] == 1
    assert data["channels"]["main"]["runs"] == 3
    assert data["channels"]["main"]["last"]["template"] == "y"


def test_failed_expand_does_not_advance(store):
    def boom(token, seed):
        raise RuntimeError("impact down")

    with pytest.raises(RuntimeError):
        store.run(boom)
    with pytest.raises(ConsoleError, match="empty text"):
        store.run(lambda t, s: "   ")
    with pytest.raises(ConsoleError, match="does not exist"):
        store.run(lambda t, s: t)  # wildcard left unexpanded
    assert store.run(fake_expand).plan.index == 1
    assert store.load_state()["channels"]["main"]["runs"] == 1


def test_seed_used_is_the_previewed_seed(store):
    pv = store.preview()
    r = store.run(fake_expand)
    assert pv["upcoming"][0]["seed"] == r.plan.seed
    assert r.prompt.endswith(f"#{r.plan.seed}")


def test_corrupt_files_backed_up_and_defaults_used(store):
    store.run(fake_expand)
    with open(store.state_path, "w", encoding="utf-8") as f:
        f.write("{not json")
    with open(store.config_path, "w", encoding="utf-8") as f:
        f.write("[1,2]")
    assert store.load_config()["categories"] == []
    assert read(store.config_path + ".bak") == "[1,2]"
    assert store.load_state()["channels"]["main"]["runs"] == 0
    assert read(store.state_path + ".bak") == "{not json"
    assert json.loads(read(store.state_path))["schema_version"] == 1
    assert any("backup" in w for w in store.last_warnings)


def test_future_schema_version_backed_up(store):
    with open(store.state_path, "w", encoding="utf-8") as f:
        json.dump({"schema_version": 99, "channels": {}}, f)
    assert store.load_state()["channels"]["main"]["runs"] == 0
    assert os.path.exists(store.state_path + ".bak")


def test_no_tmp_files_left(store):
    for _ in range(3):
        store.run(fake_expand)
    assert not [f for f in os.listdir(store.root) if f.endswith(".tmp")]


def test_concurrent_runs_and_rest_calls_count_exactly(store):
    store.save_config(cfg(("a", [("x", 1000)])))
    errors = []

    def worker():
        try:
            for _ in range(25):
                store.run(fake_expand)
                store.preview()
                store.fingerprint()
        except Exception as e:  # pragma: no cover - reported below
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    ch = store.load_state()["channels"]["main"]
    assert ch["runs"] == 200
    assert ch["done"] == 200


def test_config_edit_while_running_revalidates_cursor(store):
    store.run(fake_expand)  # a.x done=1
    store.save_config(cfg(("a", [("y", 1)]), ("b", [("z", 1)])))
    st = store.load_state()["channels"]["main"]
    assert (st["category"], st["template"], st["done"]) == ("a", "y", 0)
    assert store.run(fake_expand).plan.template == "y"


def test_config_edit_disabling_everything_keeps_state_and_errors_clearly(store):
    store.run(fake_expand)
    store.save_config(cfg(("a", [("x", 2, False)])))
    with pytest.raises(ConsoleError, match="no template is enabled"):
        store.run(fake_expand)
    assert store.load_state()["channels"]["main"]["runs"] == 1


def test_overrides_do_not_touch_config_file(store):
    before = read(store.config_path)
    r = store.run(fake_expand, overrides="a=off")
    assert r.plan.template == "z"
    assert read(store.config_path) == before


def test_reset_skip_select(store):
    store.run(fake_expand)
    store.skip()
    assert store.plan().template == "y"
    store.select("b", "z")
    assert store.plan().template == "z"
    store.reset()
    assert store.plan().template == "x"


def test_events_emitted_and_listener_errors_ignored(store):
    seen = []
    store.listeners.append(lambda kind, payload: seen.append(kind))
    store.listeners.append(lambda kind, payload: 1 / 0)
    store.run(fake_expand)
    store.reset()
    assert seen == ["state", "run", "state"]


def test_system_prompt_only_when_llm_enabled(store):
    r = store.run(fake_expand, resolve_system_prompt=lambda name: f"TEXT[{name}]")
    assert r.system_prompt_text == ""
    r = store.run(fake_expand, overrides="llm=on", resolve_system_prompt=lambda name: f"TEXT[{name}]")
    assert r.system_prompt_text == "TEXT[sp_a]"


def test_pin_run_does_not_move_counter(store):
    r = store.run(fake_expand, pin='{"category":"a","template":"y","seed":77}')
    assert (r.plan.mode, r.plan.template, r.prompt) == ("pin", "y", "T:y#77")
    after = store.load_state()["channels"]["main"]
    assert after["category"] is None
    assert after["runs"] == 1


def test_fingerprint_moves_after_each_run(store):
    fps = []
    for _ in range(3):
        fps.append(store.fingerprint())
        store.run(fake_expand)
    assert len(set(fps)) == 3
