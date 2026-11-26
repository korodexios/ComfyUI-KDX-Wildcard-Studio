"""KDX Wildcard Studio engine — pure functions over plain dicts (no ComfyUI, no I/O).

Model
-----
config = {
  "schema_version": 1,
  "llm_enabled": bool,
  "show_nsfw": bool,                                      # NSFW templates in Add/Import and in the Gallery
  "mode": "sequential" | "manual" | "pin",
  "select": {"category": key, "template": name} | None,   # manual / pin target
  "pin_seed": int | None,                                  # pin mode seed
  "wildcard_dirs": [str],                                  # wildcard roots; [] = automatic
  "ignored": [str],                                        # templates removed in the panel; Import skips them
  "categories": [ {"key", "name", "enabled", "system_prompt", "on_end",
                   "templates": [ {"name", "enabled", "repeat"} ]} ]
}
state = {"schema_version": 1, "channels": {"main": channel}}
channel = {"category", "template", "cat_index", "tpl_index", "done", "runs",
           "next_seed", "stopped", "message", "last"}

The cursor (category, template, done) points at the *next* image. A run renders at
the cursor and ``commit`` moves it. Names are the identity; the index hints are only
used to land near the old spot when the config was edited and a name disappeared.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import secrets
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Callable

SCHEMA_VERSION = 1
DEFAULT_CHANNEL = "main"
MODES = ("sequential", "manual", "pin")
ON_END = ("loop", "next", "stop")
DEFAULT_ON_END = "next"
DEFAULT_REPEAT = 1
MAX_REPEAT = 100_000
SEED_MAX = 2**31 - 1
TEMPLATE_PREFIX = "templates/"

_KEY_RE = re.compile(r"[^a-z0-9_\-]+")

SeedFn = Callable[[], int]


class ConsoleError(Exception):
    """A user-facing problem (shown in the ComfyUI error dialog / panel as is)."""


class ConsoleFinished(ConsoleError):
    """A category with on_end = stop has rendered everything. Not a fault: the node blocks the run
    quietly and shows this message instead of an error."""


def random_seed() -> int:
    return secrets.randbelow(SEED_MAX + 1)


def slug(text: str) -> str:
    """Category key used by overrides (``art``, ``osoba_a_portret``)."""
    ascii_text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode("ascii")
    s = _KEY_RE.sub("_", ascii_text.strip().lower()).strip("_")
    return s or "category"


# --------------------------------------------------------------------------- config


def default_config() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "llm_enabled": False,
        "show_nsfw": False,
        "mode": "sequential",
        "select": None,
        "pin_seed": None,
        "wildcard_dirs": [],
        "ignored": [],
        "categories": [],
    }


def _bool(v, default: bool) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        low = v.strip().lower()
        if low in ("1", "true", "on", "yes"):
            return True
        if low in ("0", "false", "off", "no"):
            return False
    return default


def _int(v, default: int | None, lo: int, hi: int) -> int | None:
    if isinstance(v, bool) or v is None:
        return default
    try:
        n = int(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def normalize_config(raw) -> tuple[dict, list[str]]:
    """Return a valid config built from ``raw`` plus human-readable warnings.

    Never raises: unusable parts are dropped/clamped and reported."""
    warnings: list[str] = []
    cfg = default_config()
    if not isinstance(raw, dict):
        if raw is not None:
            warnings.append("config is not an object, defaults used")
        return cfg, warnings

    cfg["llm_enabled"] = _bool(raw.get("llm_enabled"), False)
    cfg["show_nsfw"] = _bool(raw.get("show_nsfw"), False)
    mode = raw.get("mode", "sequential")
    if mode not in MODES:
        warnings.append(f"unknown mode {mode!r}, using 'sequential'")
        mode = "sequential"
    cfg["mode"] = mode
    cfg["pin_seed"] = _int(raw.get("pin_seed"), None, 0, SEED_MAX)
    dirs = raw.get("wildcard_dirs") or []
    if isinstance(dirs, str):
        dirs = [dirs]
    if not isinstance(dirs, list):
        warnings.append("'wildcard_dirs' is not a list, using the automatic folders")
        dirs = []
    for d in dirs:
        d = str(d).strip() if isinstance(d, str) else ""
        if d and d not in cfg["wildcard_dirs"]:
            cfg["wildcard_dirs"].append(d)

    ign = raw.get("ignored") or []
    if isinstance(ign, list):
        for n in ign:
            n = template_name(n) if isinstance(n, str) else ""
            if n and n not in cfg["ignored"]:
                cfg["ignored"].append(n)

    seen_keys: set[str] = set()
    cats_raw = raw.get("categories", [])
    if not isinstance(cats_raw, list):
        warnings.append("'categories' is not a list")
        cats_raw = []
    for i, c in enumerate(cats_raw):
        if not isinstance(c, dict):
            warnings.append(f"category #{i + 1} is not an object, skipped")
            continue
        name = str(c.get("name") or c.get("key") or f"Category {i + 1}").strip()
        key = slug(c.get("key") or name)
        base, n = key, 2
        while key in seen_keys:
            key = f"{base}_{n}"
            n += 1
        if c.get("key") and slug(c["key"]) != key:
            warnings.append(f"duplicate category key {c['key']!r} renamed to {key!r}")
        seen_keys.add(key)
        on_end = c.get("on_end", DEFAULT_ON_END)
        if on_end not in ON_END:
            warnings.append(f"category {key!r}: unknown on_end {on_end!r}, using {DEFAULT_ON_END!r}")
            on_end = DEFAULT_ON_END
        tpls = []
        seen_tpl: set[str] = set()
        tpls_raw = c.get("templates", [])
        if not isinstance(tpls_raw, list):
            warnings.append(f"category {key!r}: 'templates' is not a list")
            tpls_raw = []
        for t in tpls_raw:
            if isinstance(t, str):
                t = {"name": t}
            if not isinstance(t, dict) or not str(t.get("name") or "").strip():
                warnings.append(f"category {key!r}: template without a name skipped")
                continue
            tname = template_name(t["name"])
            if tname in seen_tpl:
                warnings.append(f"category {key!r}: duplicate template {tname!r} skipped")
                continue
            seen_tpl.add(tname)
            rep = _int(t.get("repeat"), DEFAULT_REPEAT, 1, MAX_REPEAT)
            tpls.append({"name": tname, "enabled": _bool(t.get("enabled"), True), "repeat": rep})
        cfg["categories"].append({
            "key": key,
            "name": name,
            "enabled": _bool(c.get("enabled"), True),
            "system_prompt": str(c.get("system_prompt") or ""),
            "on_end": on_end,
            "templates": tpls,
        })

    sel = raw.get("select")
    if isinstance(sel, dict) and sel.get("category") and sel.get("template"):
        cfg["select"] = {"category": str(sel["category"]), "template": template_name(sel["template"])}
    elif isinstance(sel, str) and "." in sel:
        ck, tn = sel.split(".", 1)
        cfg["select"] = {"category": ck.strip(), "template": template_name(tn)}
    return cfg, warnings


def template_name(name) -> str:
    """``__templates/portrait__`` / ``templates/portrait`` / ``portrait`` -> ``portrait``."""
    s = str(name or "").strip().strip("_").strip()
    if s.startswith(TEMPLATE_PREFIX):
        s = s[len(TEMPLATE_PREFIX):]
    return s


def template_token(name: str) -> str:
    return f"__{TEMPLATE_PREFIX}{template_name(name)}__"


def find_category(cfg: dict, key: str) -> int | None:
    for i, c in enumerate(cfg["categories"]):
        if c["key"] == key:
            return i
    return None


def find_template(cat: dict, name: str) -> int | None:
    for i, t in enumerate(cat["templates"]):
        if t["name"] == name:
            return i
    return None


def config_hash(cfg: dict) -> str:
    return hashlib.sha1(json.dumps(cfg, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------- state


def default_channel(seed_fn: SeedFn = random_seed) -> dict:
    return {
        "category": None,
        "template": None,
        "cat_index": 0,
        "tpl_index": 0,
        "done": 0,
        "runs": 0,
        "next_seed": seed_fn(),
        "stopped": False,
        "message": "",
        "last": None,
    }


def default_state() -> dict:
    return {"schema_version": SCHEMA_VERSION, "channels": {}}


def normalize_state(raw, seed_fn: SeedFn = random_seed) -> tuple[dict, list[str]]:
    warnings: list[str] = []
    state = default_state()
    if not isinstance(raw, dict):
        if raw is not None:
            warnings.append("state is not an object, empty state used")
        return state, warnings
    chans = raw.get("channels", {})
    if not isinstance(chans, dict):
        warnings.append("'channels' is not an object")
        chans = {}
    for name, ch in chans.items():
        if not isinstance(ch, dict):
            warnings.append(f"channel {name!r} is not an object, dropped")
            continue
        d = default_channel(seed_fn)
        d["category"] = ch.get("category") if isinstance(ch.get("category"), str) else None
        d["template"] = ch.get("template") if isinstance(ch.get("template"), str) else None
        d["cat_index"] = _int(ch.get("cat_index"), 0, 0, 1_000_000)
        d["tpl_index"] = _int(ch.get("tpl_index"), 0, 0, 1_000_000)
        d["done"] = _int(ch.get("done"), 0, 0, MAX_REPEAT)
        d["runs"] = _int(ch.get("runs"), 0, 0, 2**62)
        ns = _int(ch.get("next_seed"), None, 0, SEED_MAX)
        if ns is not None:
            d["next_seed"] = ns
        d["stopped"] = _bool(ch.get("stopped"), False)
        d["message"] = str(ch.get("message") or "")
        d["last"] = ch.get("last") if isinstance(ch.get("last"), dict) else None
        state["channels"][str(name)] = d
    return state, warnings


def get_channel(state: dict, channel: str = DEFAULT_CHANNEL, seed_fn: SeedFn = random_seed) -> dict:
    """Channel dict (created in ``state`` when missing)."""
    ch = state["channels"].get(channel)
    if ch is None:
        ch = default_channel(seed_fn)
        state["channels"][channel] = ch
    return ch


# --------------------------------------------------------------------------- cursor


def _tpl_on(cat: dict, ti: int) -> bool:
    return bool(cat["enabled"] and cat["templates"][ti]["enabled"])


def _first_enabled_tpl(cat: dict, start: int = 0) -> int | None:
    if not cat["enabled"]:
        return None
    for ti in range(start, len(cat["templates"])):
        if cat["templates"][ti]["enabled"]:
            return ti
    return None


def _next_category(cfg: dict, ci: int) -> tuple[int, int] | None:
    """First enabled template in the categories after ``ci`` (wrapping, ``ci`` itself last)."""
    cats = cfg["categories"]
    n = len(cats)
    for step in range(1, n + 1):
        cj = (ci + step) % n
        ti = _first_enabled_tpl(cats[cj])
        if ti is not None:
            return cj, ti
    return None


def any_enabled(cfg: dict) -> bool:
    return any(_first_enabled_tpl(c) is not None for c in cfg["categories"])


NOTHING_ENABLED = (
    "KDX Wildcard Studio: no template is enabled. Enable at least one category and template in the panel "
    "(or import templates), or check 'overrides'."
)


def locate(cfg: dict, ch: dict) -> tuple[int, int, int]:
    """Validate the channel cursor against ``cfg`` and return ``(ci, ti, done)``.

    * names win; a missing name falls back to the stored index (clamped) with done=0
    * a disabled item at the cursor is skipped forward: next enabled template in the
      same category (wrapping inside it when the category loops), else the next
      enabled category
    * raises ConsoleError when nothing is enabled"""
    cats = cfg["categories"]
    if not any_enabled(cfg):
        raise ConsoleError(NOTHING_ENABLED)
    done = int(ch.get("done") or 0)

    ci = find_category(cfg, ch.get("category")) if ch.get("category") else None
    if ci is None:
        ci = min(int(ch.get("cat_index") or 0), len(cats) - 1)
        done = 0
        moved_cat = True
    else:
        moved_cat = False
    cat = cats[ci]
    ti = None if moved_cat else (find_template(cat, ch.get("template")) if ch.get("template") else None)
    if ti is None:
        done = 0
        if not cat["templates"]:
            nxt = _next_category(cfg, ci)
            assert nxt is not None  # any_enabled() guarantees one
            return nxt[0], nxt[1], 0
        ti = 0 if moved_cat else min(int(ch.get("tpl_index") or 0), len(cat["templates"]) - 1)

    if _tpl_on(cat, ti):
        rep = cat["templates"][ti]["repeat"]
        return ci, ti, min(done, rep - 1)

    nt = _first_enabled_tpl(cat, ti + 1)
    if nt is None and cat["on_end"] == "loop":
        nt = _first_enabled_tpl(cat, 0)
    if nt is not None:
        return ci, nt, 0
    nxt = _next_category(cfg, ci)
    assert nxt is not None
    return nxt[0], nxt[1], 0


def _set_cursor(ch: dict, cfg: dict, ci: int, ti: int, done: int) -> None:
    cat = cfg["categories"][ci]
    ch["category"] = cat["key"]
    ch["template"] = cat["templates"][ti]["name"]
    ch["cat_index"] = ci
    ch["tpl_index"] = ti
    ch["done"] = done


def _step_after_template(cfg: dict, ch: dict, ci: int, ti: int, honor_stop: bool) -> None:
    """Move the cursor past template ``ti`` (its repeats are used up)."""
    cat = cfg["categories"][ci]
    nt = _first_enabled_tpl(cat, ti + 1)
    if nt is not None:
        _set_cursor(ch, cfg, ci, nt, 0)
        return
    on_end = cat["on_end"]
    if on_end == "loop":
        nt = _first_enabled_tpl(cat, 0)
        if nt is not None:
            _set_cursor(ch, cfg, ci, nt, 0)
            return
    nxt = _next_category(cfg, ci)
    if nxt is None:  # everything got disabled meanwhile
        _set_cursor(ch, cfg, ci, ti, 0)
        return
    _set_cursor(ch, cfg, nxt[0], nxt[1], 0)
    if on_end == "stop" and honor_stop:
        ch["stopped"] = True
        ch["message"] = (
            f"KDX Wildcard Studio: category '{cat['name']}' is finished (on_end = stop), nothing more to render. "
            "Press Skip or Reset in the panel to continue, or change on_end."
        )


# --------------------------------------------------------------------------- plan / commit


@dataclass
class Plan:
    mode: str
    category: str
    category_name: str
    template: str
    seed: int
    system_prompt: str  # KDX-LLM profile name
    done: int  # images already made from this template before this run
    repeat: int
    channel: str = DEFAULT_CHANNEL
    llm_enabled: bool = False
    cursor: tuple[int, int] | None = None  # (ci, ti) for sequential commits

    @property
    def index(self) -> int:
        """1-based number of this image within the template's repeat block."""
        return self.done + 1

    @property
    def repeat_left(self) -> int:
        return max(0, self.repeat - self.done - 1)

    @property
    def token(self) -> str:
        return template_token(self.template)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("cursor", None)
        d["index"] = self.index
        d["repeat_left"] = self.repeat_left
        return d


@dataclass
class Pin:
    """Exact reproduction request (from the image metadata or the panel)."""

    template: str
    seed: int
    category: str = ""
    system_prompt: str | None = None
    index: int = 1
    repeat: int = 1
    extra: dict = field(default_factory=dict)

    @classmethod
    def parse(cls, text) -> Pin | None:
        if isinstance(text, dict):
            data = text
        else:
            s = str(text or "").strip()
            if not s:
                return None
            try:
                data = json.loads(s)
            except ValueError as e:
                raise ConsoleError(f"KDX Wildcard Studio: invalid 'pin' ({e}). Clear the pin to return to normal mode.") from e
        if not isinstance(data, dict):
            raise ConsoleError("KDX Wildcard Studio: 'pin' must be a JSON object.")
        tpl = template_name(data.get("template", ""))
        seed = _int(data.get("seed"), None, 0, SEED_MAX)
        if not tpl or seed is None:
            raise ConsoleError("KDX Wildcard Studio: 'pin' needs 'template' and 'seed'.")
        sp = data.get("system_prompt")
        return cls(
            template=tpl,
            seed=seed,
            category=str(data.get("category") or ""),
            system_prompt=sp if isinstance(sp, str) else None,
            index=_int(data.get("index"), 1, 1, MAX_REPEAT),
            repeat=_int(data.get("repeat"), 1, 1, MAX_REPEAT),
        )

    def to_json(self) -> str:
        d = {"category": self.category, "template": self.template, "seed": self.seed,
             "index": self.index, "repeat": self.repeat}
        if self.system_prompt is not None:
            d["system_prompt"] = self.system_prompt
        return json.dumps(d, ensure_ascii=False, sort_keys=True)


def _selected(cfg: dict, select: dict | None, what: str) -> tuple[int, int]:
    if not select:
        raise ConsoleError(f"KDX Wildcard Studio: {what} mode needs a selected template (select=category.template).")
    ci = find_category(cfg, select.get("category"))
    if ci is None:
        raise ConsoleError(f"KDX Wildcard Studio: selected category {select.get('category')!r} does not exist.")
    ti = find_template(cfg["categories"][ci], template_name(select.get("template")))
    if ti is None:
        raise ConsoleError(
            f"KDX Wildcard Studio: template {select.get('template')!r} is not in category {select.get('category')!r}."
        )
    return ci, ti


def plan(cfg: dict, state: dict, *, channel: str = DEFAULT_CHANNEL, mode: str | None = None,
         select: dict | None = None, seed: int | None = None, pin: Pin | None = None,
         seed_fn: SeedFn = random_seed) -> Plan:
    """What the next run renders. ``cfg`` is the *effective* config (overrides applied);
    ``mode``/``select``/``seed`` are per-run overrides. Does not mutate the state."""
    llm = bool(cfg.get("llm_enabled"))
    ch = copy.deepcopy(state["channels"].get(channel) or default_channel(seed_fn))
    mode = mode or cfg.get("mode") or "sequential"
    if pin is not None:
        mode = "pin"

    if mode == "pin":
        if pin is None:
            sel = select or cfg.get("select")
            ci, ti = _selected(cfg, sel, "pin")
            pseed = seed if seed is not None else cfg.get("pin_seed")
            if pseed is None:
                raise ConsoleError("KDX Wildcard Studio: pin mode needs a seed (pin_seed in the panel or seed= in overrides).")
            cat = cfg["categories"][ci]
            pin = Pin(template=cat["templates"][ti]["name"], seed=int(pseed), category=cat["key"],
                      system_prompt=cat["system_prompt"])
        ci = find_category(cfg, pin.category) if pin.category else None
        cat = cfg["categories"][ci] if ci is not None else None
        sp = pin.system_prompt if pin.system_prompt is not None else (cat["system_prompt"] if cat else "")
        return Plan(mode="pin", category=pin.category, category_name=cat["name"] if cat else pin.category,
                    template=pin.template, seed=pin.seed if seed is None else int(seed), system_prompt=sp,
                    done=pin.index - 1, repeat=max(pin.repeat, pin.index), channel=channel, llm_enabled=llm)

    if mode == "manual":
        ci, ti = _selected(cfg, select or cfg.get("select"), "manual")
        cat = cfg["categories"][ci]
        return Plan(mode="manual", category=cat["key"], category_name=cat["name"],
                    template=cat["templates"][ti]["name"], seed=ch["next_seed"] if seed is None else int(seed),
                    system_prompt=cat["system_prompt"], done=0, repeat=1, channel=channel, llm_enabled=llm,
                    cursor=(ci, ti))

    if ch.get("stopped"):
        raise ConsoleFinished(ch.get("message") or "KDX Wildcard Studio: finished (on_end = stop). Press Skip or Reset.")
    ci, ti, done = locate(cfg, ch)
    cat = cfg["categories"][ci]
    tpl = cat["templates"][ti]
    return Plan(mode="sequential", category=cat["key"], category_name=cat["name"], template=tpl["name"],
                seed=ch["next_seed"] if seed is None else int(seed), system_prompt=cat["system_prompt"],
                done=done, repeat=tpl["repeat"], channel=channel, llm_enabled=llm, cursor=(ci, ti))


def commit(cfg: dict, state: dict, p: Plan, *, last: dict | None = None,
           seed_fn: SeedFn = random_seed) -> dict:
    """Return a new state with the run ``p`` accounted for (call only after success)."""
    new = copy.deepcopy(state)
    ch = get_channel(new, p.channel, seed_fn)
    ch["runs"] = int(ch.get("runs") or 0) + 1
    if last is not None:
        ch["last"] = last
    if p.mode == "pin":
        return new
    ch["next_seed"] = seed_fn()
    if p.mode == "manual":
        return new
    ci, ti = p.cursor  # type: ignore[misc]
    done = p.done + 1
    if done < p.repeat:
        _set_cursor(ch, cfg, ci, ti, done)
    else:
        _step_after_template(cfg, ch, ci, ti, honor_stop=True)
    return new


# --------------------------------------------------------------------------- user actions


def reset(state: dict, channel: str = DEFAULT_CHANNEL, seed_fn: SeedFn = random_seed) -> dict:
    new = copy.deepcopy(state)
    new["channels"][channel] = default_channel(seed_fn)
    return new


def skip(cfg: dict, state: dict, channel: str = DEFAULT_CHANNEL, seed_fn: SeedFn = random_seed) -> dict:
    """Jump to the next template now. When stopped, only clears the stop (the cursor is already past)."""
    new = copy.deepcopy(state)
    ch = get_channel(new, channel, seed_fn)
    if ch.get("stopped"):
        ch["stopped"] = False
        ch["message"] = ""
        return new
    ci, ti, _ = locate(cfg, ch)
    _step_after_template(cfg, ch, ci, ti, honor_stop=False)
    return new


def select_cursor(cfg: dict, state: dict, category: str, template: str,
                  channel: str = DEFAULT_CHANNEL, seed_fn: SeedFn = random_seed) -> dict:
    """Put the sequential cursor on ``category.template`` (done=0) and clear a stop."""
    ci, ti = _selected(cfg, {"category": category, "template": template}, "select")
    new = copy.deepcopy(state)
    ch = get_channel(new, channel, seed_fn)
    _set_cursor(ch, cfg, ci, ti, 0)
    ch["stopped"] = False
    ch["message"] = ""
    return new


def preview(cfg: dict, state: dict, *, count: int = 5, channel: str = DEFAULT_CHANNEL, mode: str | None = None,
            select: dict | None = None, seed: int | None = None, pin: Pin | None = None) -> dict:
    """Upcoming runs (simulated on a copy). The first plan uses the real stored seed;
    later seeds are not known yet (shown as None)."""
    out: list[dict] = []
    st = copy.deepcopy(state)
    error = None
    for i in range(max(1, count)):
        try:
            p = plan(cfg, st, channel=channel, mode=mode, select=select, seed=seed, pin=pin)
        except ConsoleError as e:
            error = str(e)
            break
        d = p.to_dict()
        if i > 0 and seed is None and p.mode != "pin":
            d["seed"] = None
        out.append(d)
        if p.mode == "pin":
            break
        st = commit(cfg, st, p, seed_fn=lambda: 0)
    return {"upcoming": out, "error": error}


def fingerprint(cfg: dict, state: dict, *, channel: str = DEFAULT_CHANNEL, overrides: str = "",
                pin: str = "") -> str:
    """IS_CHANGED value: changes whenever the next run would differ (never NaN)."""
    pin = (pin or "").strip()
    if pin:
        payload = {"pin": pin, "cfg": config_hash(cfg), "ov": overrides or ""}
    else:
        ch = state["channels"].get(channel) or {}
        payload = {"ch": {k: ch.get(k) for k in ("category", "template", "done", "runs", "next_seed", "stopped")},
                   "cfg": config_hash(cfg), "ov": overrides or ""}
    return hashlib.sha1(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
