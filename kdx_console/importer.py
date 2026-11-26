"""Build/merge the category list from template folders.

``templates/<folder>/<name>`` -> category ``<folder>`` with template ``<folder>/<name>``;
flat ``templates/<name>`` -> category ``templates`` (display "Templates").
Existing categories and template settings (enabled, repeat, on_end, system_prompt) are kept;
new templates are appended in sorted order, so the config order stays what the user had.
NSFW names never get here (``wildcards.filter_templates``).
"""

from __future__ import annotations

import copy

from . import engine

FLAT_KEY = "templates"
FLAT_NAME = "Templates"


def group(names: list[str]) -> list[tuple[str, str, list[str]]]:
    """``[(category key, display name, [template names])]`` in first-seen order of sorted names."""
    cats: dict[str, tuple[str, list[str]]] = {}
    for n in sorted(names):
        if "/" in n:
            folder = n.split("/", 1)[0]
            key, disp = engine.slug(folder), folder
        else:
            key, disp = FLAT_KEY, FLAT_NAME
        cats.setdefault(key, (disp, []))[1].append(n)
    return [(k, d, t) for k, (d, t) in cats.items()]


def merge(cfg: dict, names: list[str], *, prune: bool = False,
          existing: list[str] | None = None) -> tuple[dict, dict]:
    """Return (new raw config, report). ``names`` are the templates that may be added; ``existing`` are all
    templates that have a file (default ``names``). Only a template without a file is "missing", and only
    such a template is removed by ``prune``: one excluded from auto-import but kept by the user stays."""
    new = copy.deepcopy(cfg)
    known = set(names) | set(existing or [])
    report = {"added": [], "missing": [], "removed": [], "categories_added": []}
    for c in new["categories"]:
        keep = []
        for t in c["templates"]:
            if t["name"] in known:
                keep.append(t)
            else:
                report["missing"].append(f"{c['key']}.{t['name']}")
                if not prune:
                    keep.append(t)
        if prune:
            report["removed"] = list(report["missing"])
        c["templates"] = keep
    present = {t["name"] for c in new["categories"] for t in c["templates"]}
    present |= set(new.get("ignored") or [])  # removed in the panel: do not bring them back
    for key, disp, tpls in group(names):
        fresh = [t for t in tpls if t not in present]
        if not fresh:
            continue
        ci = engine.find_category(new, key)
        if ci is None:
            new["categories"].append({"key": key, "name": disp, "enabled": True, "system_prompt": "",
                                      "on_end": engine.DEFAULT_ON_END, "templates": []})
            ci = len(new["categories"]) - 1
            report["categories_added"].append(key)
        for t in fresh:
            new["categories"][ci]["templates"].append({"name": t, "enabled": True, "repeat": engine.DEFAULT_REPEAT})
            report["added"].append(f"{key}.{t}")
    return new, report
