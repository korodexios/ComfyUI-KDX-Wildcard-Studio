"""Browser cache: ComfyUI sends no Cache-Control for .mjs files, so every relative module import carries
``?v=<package version>``. A new release then loads fresh panel code instead of a cached copy."""

import os
import re

from _helpers import ROOT

WEB = os.path.join(ROOT, "web")
IMPORT_RE = re.compile(r'from\s+"(\./[^"]+\.mjs[^"]*)"')


def version():
    with open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8") as f:
        return re.search(r'^version\s*=\s*"([^"]+)"', f.read(), re.M).group(1)


def test_every_relative_module_import_is_versioned():
    v = version()
    found = 0
    for dirpath, _dirs, files in os.walk(WEB):
        for name in files:
            if not name.endswith((".js", ".mjs")):
                continue
            with open(os.path.join(dirpath, name), encoding="utf-8") as f:
                for spec in IMPORT_RE.findall(f.read()):
                    found += 1
                    assert spec.endswith(f"?v={v}"), f"{name}: {spec} (expected ?v={v})"
    assert found >= 5


DYNAMIC_RE = re.compile(r'import\(\s*"(\./[^"]+\.mjs[^"]*)"\s*\)')


def test_lazy_module_imports_are_versioned():
    """The Gallery and the Template builder are loaded on click with import("./x.mjs?v=...")."""
    v = version()
    found = set()
    for dirpath, _dirs, files in os.walk(WEB):
        for name in files:
            if name.endswith((".js", ".mjs")):
                with open(os.path.join(dirpath, name), encoding="utf-8") as f:
                    for spec in DYNAMIC_RE.findall(f.read()):
                        assert spec.endswith(f"?v={v}"), f"{name}: {spec} (expected ?v={v})"
                        found.add(spec.split("?")[0])
    assert {"./gallery.mjs", "./builder.mjs"} <= found
