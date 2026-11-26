"""Per-workflow settings: the hidden ``scope`` widget of the Studio node.

The shared config keeps the categories, templates and their settings. A workflow can switch
categories and templates on or off for itself and keep its own counter (a state channel):

    {"channel": "w_3f9a1c2b", "set": {"art": false, "portrait.selfie": true}}

``set`` only lists what differs from the shared config; everything else follows it. Keys that no
longer exist (a template removed in the panel) are ignored, so an old workflow never fails a run.
An empty string means "shared": the workflow uses the shared on/off and the ``main`` counter.
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field

from .engine import DEFAULT_CHANNEL, ConsoleError, find_category, find_template

_CHANNEL_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


@dataclass
class Scope:
    channel: str = DEFAULT_CHANNEL
    set: dict[str, bool] = field(default_factory=dict)

    @property
    def shared(self) -> bool:
        return self.channel == DEFAULT_CHANNEL and not self.set


def parse(text) -> Scope:
    """``""`` / ``None`` -> shared scope; a JSON object (or dict) -> its channel and on/off map."""
    if isinstance(text, dict):
        data = text
    else:
        s = str(text or "").strip()
        if not s:
            return Scope()
        try:
            data = json.loads(s)
        except ValueError as e:
            raise ConsoleError(f"KDX Wildcard Studio: the workflow settings (scope) are not valid JSON: {e}") from None
    if not isinstance(data, dict):
        raise ConsoleError("KDX Wildcard Studio: the workflow settings (scope) must be a JSON object.")
    ch = str(data.get("channel") or DEFAULT_CHANNEL)
    if not _CHANNEL_RE.match(ch):
        raise ConsoleError(f"KDX Wildcard Studio: invalid counter name {ch!r} in the workflow settings.")
    raw = data.get("set") or {}
    if not isinstance(raw, dict):
        raise ConsoleError("KDX Wildcard Studio: 'set' in the workflow settings must be an object.")
    return Scope(channel=ch, set={str(k).strip(): bool(v) for k, v in raw.items() if str(k).strip()})


def apply(cfg: dict, sc: Scope) -> dict:
    """Effective config for this workflow (a copy when anything changes; unknown keys are skipped)."""
    if not sc.set:
        return cfg
    eff = copy.deepcopy(cfg)
    for key, on in sc.set.items():
        ck, _, tn = key.partition(".")
        ci = find_category(eff, ck)
        if ci is None:
            continue
        cat = eff["categories"][ci]
        if not tn:
            cat["enabled"] = on
            continue
        ti = find_template(cat, tn)
        if ti is not None:
            cat["templates"][ti]["enabled"] = on
    return eff
