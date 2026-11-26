"""Shared test setup: make the ``kdx_console`` package importable."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class SeqSeeds:
    """Deterministic seed source: 1000, 1001, ..."""

    def __init__(self, start=1000):
        self.n = start

    def __call__(self):
        v = self.n
        self.n += 1
        return v


def fake_expand(token, seed):
    """Stand-in for Impact ``process``: echoes the template and seed."""
    return f"{token}#{seed}".replace("__templates/", "T:").replace("__#", "#")


def cfg(*cats, **top):
    """Build a raw config: cfg(("a", [("x", 2), ("y", 1)], "next"), ...)."""
    out = {"schema_version": 1, "categories": []}
    out.update(top)
    for c in cats:
        key, tpls = c[0], c[1]
        on_end = c[2] if len(c) > 2 else "next"
        out["categories"].append({
            "key": key, "name": key.upper(), "on_end": on_end, "system_prompt": f"sp_{key}",
            "templates": [{"name": t[0], "repeat": t[1], "enabled": (t[2] if len(t) > 2 else True)} for t in tpls],
        })
    return out
