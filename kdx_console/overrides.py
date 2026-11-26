"""Per-run ``overrides`` string (remote control over a plain STRING wire).

Grammar: items separated by ``,`` ``;`` or a newline, each
``key=value`` (or ``key:value``), case-insensitive, applied left to right, ``#`` = comment.

    art=off                  category (key) on/off
    portrait.selfie=on       template in a category on/off
    *=off                    all categories;   art.*=off   all templates of a category
    select=art.cubism        target for manual/pin (implies manual without ``mode``)
    mode=sequential|manual|pin
    seed=123                 wildcard seed for this run
    llm=on|off               overrides llm_enabled

On/off values: on, off, 1, 0, true, false, yes, no. Nothing is written to the config.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field

from .engine import MODES, SEED_MAX, ConsoleError, find_category, find_template, template_name

_SPLIT = re.compile(r"[,;\n]+")
_ON = {"on", "1", "true", "yes", "enable", "enabled"}
_OFF = {"off", "0", "false", "no", "disable", "disabled"}


@dataclass
class Overrides:
    toggles: list[tuple[str, str | None, bool]] = field(default_factory=list)  # (cat|"*", tpl|"*"|None, on)
    mode: str | None = None
    select: dict | None = None
    seed: int | None = None
    llm: bool | None = None
    text: str = ""

    @property
    def empty(self) -> bool:
        return not (self.toggles or self.mode or self.select or self.seed is not None or self.llm is not None)


def _onoff(key: str, value: str) -> bool:
    v = value.strip().lower()
    if v in _ON:
        return True
    if v in _OFF:
        return False
    raise ConsoleError(f"KDX Wildcard Studio overrides: '{key}={value}' — value must be on/off.")


def parse(text) -> Overrides:
    ov = Overrides(text=str(text or ""))
    for raw in _SPLIT.split(ov.text):
        item = raw.strip()
        if not item or item.startswith("#"):
            continue
        m = re.match(r"^([^=:]+)[=:](.*)$", item)
        if not m:
            raise ConsoleError(f"KDX Wildcard Studio overrides: '{item}' — expected key=value.")
        key, value = m.group(1).strip().lower(), m.group(2).strip()
        if key == "mode":
            v = value.lower()
            if v not in MODES:
                raise ConsoleError(f"KDX Wildcard Studio overrides: mode={value} — allowed: {', '.join(MODES)}.")
            ov.mode = v
        elif key == "select":
            if "." not in value:
                raise ConsoleError(f"KDX Wildcard Studio overrides: select={value} — expected category.template.")
            c, t = value.split(".", 1)
            ov.select = {"category": c.strip().lower(), "template": template_name(t)}
        elif key == "seed":
            try:
                s = int(value)
            except ValueError:
                raise ConsoleError(f"KDX Wildcard Studio overrides: seed={value} is not a number.") from None
            if not 0 <= s <= SEED_MAX:
                raise ConsoleError(f"KDX Wildcard Studio overrides: seed must be 0..{SEED_MAX}.")
            ov.seed = s
        elif key == "llm":
            ov.llm = _onoff(key, value)
        else:
            if "." in key:
                c, t = key.split(".", 1)
                ov.toggles.append((c.strip(), template_name(t), _onoff(key, value)))
            else:
                ov.toggles.append((key, None, _onoff(key, value)))
    if ov.select and not ov.mode:
        ov.mode = "manual"
    return ov


def apply(cfg: dict, ov: Overrides) -> dict:
    """Effective config for one run (a copy; the stored config is untouched)."""
    if ov.empty:
        return cfg
    eff = copy.deepcopy(cfg)
    for ck, tn, on in ov.toggles:
        cats = eff["categories"] if ck == "*" else None
        if cats is None:
            ci = find_category(eff, ck)
            if ci is None:
                known = ", ".join(c["key"] for c in eff["categories"]) or "(none)"
                raise ConsoleError(f"KDX Wildcard Studio overrides: unknown category '{ck}'. Known: {known}.")
            cats = [eff["categories"][ci]]
        for cat in cats:
            if tn is None:
                cat["enabled"] = on
            elif tn == "*":
                for t in cat["templates"]:
                    t["enabled"] = on
                if on:
                    cat["enabled"] = True
            else:
                ti = find_template(cat, tn)
                if ti is None:
                    known = ", ".join(t["name"] for t in cat["templates"]) or "(none)"
                    raise ConsoleError(
                        f"KDX Wildcard Studio overrides: template '{tn}' is not in category '{cat['key']}'. Known: {known}.")
                cat["templates"][ti]["enabled"] = on
                if on:
                    cat["enabled"] = True
    if ov.llm is not None:
        eff["llm_enabled"] = ov.llm
    return eff
