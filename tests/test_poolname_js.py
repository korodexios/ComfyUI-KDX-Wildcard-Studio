"""The New pool window's folder and name rules (web/kdx_console/poolname.mjs), run in Node; skipped without Node."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from _helpers import ROOT

from kdx_console import pools

NODE = shutil.which("node")
MODULE = Path(ROOT, "web", "kdx_console", "poolname.mjs").as_uri()

CASES = [
    # (choice, typed, name) -> (key, error contains)
    (("", "", "light_lamp"), ("", "Choose a folder")),
    (("core", "", ""), ("", "name")),
    (("core", "", "Light_Lamp"), ("core/light_lamp", "")),
    (("core", "ignored", "x"), ("core/x", "")),
    (("__new__", "", "x"), ("", "new folder")),
    (("__new__", "auto", "motor_sound"), ("auto/motor_sound", "")),
    (("__new__", "auto/motor", "rpm"), ("auto/motor/rpm", "")),
    (("__new__", "Auto Car", "x"), ("auto car/x", "a-z")),
    (("__new__", "../etc", "x"), ("../etc/x", "a-z")),
    (("__new__", "templates", "x"), ("templates/x", "reserved")),
    (("__new__", "packs/demo", "x"), ("packs/demo/x", "reserved")),
    (("core", "", "with-dash"), ("core/with-dash", "a-z, 0-9 and _")),
]


def run(script: str):
    out = subprocess.run([NODE, "--input-type=module", "-e", script], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


@pytest.mark.skipif(not NODE, reason="node is not installed")
def test_new_pool_key_rules():
    calls = ",".join(f"newPoolKey({json.dumps({'choice': c, 'typed': t, 'name': n})})" for (c, t, n), _ in CASES)
    got = run(f"import {{ newPoolKey }} from {json.dumps(MODULE)}; console.log(JSON.stringify([{calls}]))")
    for ((c, t, n), (key, err)), res in zip(CASES, got, strict=True):
        assert res["key"] == key, (c, t, n, res)
        if err:
            assert err.lower() in res["error"].lower(), (c, t, n, res)
        else:
            assert res["error"] == "" and res["token"] == f"__{key}__"
            assert pools.check_key(key, new=True) == key  # what the window accepts, the server accepts too


@pytest.mark.skipif(not NODE, reason="node is not installed")
def test_start_folder_is_never_a_guess():
    got = run(f"import {{ startFolder }} from {json.dumps(MODULE)};"
              "console.log(JSON.stringify([startFolder('core', ['activity', 'core']), startFolder('', ['activity']),"
              "startFolder('gone', ['activity'])]))")
    assert got == ["core", "", ""]


def test_module_has_no_imports():
    """Pure on purpose: Node loads it without ComfyUI."""
    text = Path(ROOT, "web", "kdx_console", "poolname.mjs").read_text(encoding="utf-8")
    assert "import " not in text and os.path.basename(MODULE) == "poolname.mjs"
