"""Template builder: a template line as a tree of bubbles, ready sentences, rule checks (pure logic).

The canvas in the panel edits a template as bubbles (text, pool tokens, ``{…|…}`` groups with weights, optional
``{…|}`` and multi-pick ``$$`` groups). ``parse_line(text)`` turns any line into bubbles and ``serialize(nodes)`` writes
it back exactly. The palette offers ready sentences ("snippets"): the block catalogue below renders one sentence per
block type and sex ("Her hair is {__person/hair__}.", expression and mood picked together, scene bundles), with the
library's default pools. ``check(text, lib, name)`` lists what breaks the library's rules (shown before saving).
No ComfyUI imports.
"""

from __future__ import annotations

import copy
import os
import random
import re
import tempfile

from .wildcard_engine import Library

SEXES = ("woman", "man", "none")
MAX_POOLS = 24
MAX_WEIGHT = 99
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_]{0,63}$")
KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_\-]*(/[a-z0-9][a-z0-9_\-]*)+$")
TOKEN_RE = re.compile(r"__([\w.\-+/*\\ ]+?)__")
RATIO_RE = re.compile(r"(?<![\d:])\d{1,2}:\d{1,2}(?![\d:])")
RANGE_RE = re.compile(r"^(\d{1,2})(?:-(\d{1,2}))?$")
CLOTHING_RE = re.compile(
    r"\b(wearing|dressed|dress|dresses|shirt|t-shirt|blouse|tank top|crop top|sweater|jumper|hoodie|cardigan|"
    r"jacket|coat|blazer|suit|trousers|pants|jeans|shorts|skirt|leggings|bra|bikini|swimsuit|lingerie|underwear|panties|briefs|"
    r"stockings|tights|socks|shoes|boots|high heels|sneakers|sandals|scarf|gloves|robe|towel|uniform|apron|"
    r"fabric|clothes|clothing|garment|outfit)\b", re.I)

#: Pose pools whose values read after "She is" (seated, lying, head down); every other pose pool after "She is posed".
POSE_IS_RE = re.compile(r"^pose/(seat_|lie_|recline_|upside_|back_|rest_|studio_(seat|lie|upside))")
#: Places that are always outdoors: the only ones core/light_sky belongs to.
OUTDOOR_PLACES = frozenset({
    "core/place_city", "core/place_grass", "core/place_jetty", "core/place_nature", "core/place_outdoor",
    "core/place_rocks", "core/place_sand", "core/place_steps", "core/place_training_outdoor", "core/place_water"})
SKY_LIGHT = "core/light_sky"
LYING_SCENE = "pose/lying_scene"
#: Scene bundles that are always indoors (their place pools are rooms and studio sets).
INDOOR_SCENES = frozenset({"pose/studio_scene", "pose/furniture_scene", "pose/furniture_scene_calm"})

PRONOUNS = {
    "woman": {"Subj": "She", "Poss": "Her", "poss": "her", "noun": "a woman"},
    "man": {"Subj": "He", "Poss": "His", "poss": "his", "noun": "a man"},
}

#: Face details of the hair block: picked {lo-hi$$ $$…} of these sentences (pools fixed).
DETAILS = [
    ("eyes", "Eyes", "{Poss} eyes are __person/eye_color__."),
    ("nose", "Nose", "{Subj} has __person/nose__."),
    ("lips", "Lips", "{Subj} has __person/lips__."),
    ("face_shape", "Face shape", "{Subj} has __person/face_shape__."),
    ("face_marks", "Face marks", "{Poss} face shows __person/facial_imperfections__."),
    ("makeup", "Makeup", "{Poss} makeup is __person/makeup__."),
    ("facial_hair", "Facial hair", "{Poss} face has __man/facial_hair__."),
]
DETAIL_IDS = [d[0] for d in DETAILS]

EXPRESSION = {f: f"person/expression_{f}" for f in ("positive", "neutral", "negative", "soft", "candid")}
SOMBER = "core/mood_somber"


def _p(*keys: str) -> list[dict]:
    return [{"key": k, "w": 1} for k in keys]


#: Block catalogue, in sentence order. ``people``: only for a woman or a man. ``default``: per sex or "*".
BLOCKS: list[dict] = [
    {"id": "medium", "label": "Medium", "people": False, "glue": "The image is …",
     "slots": [{"id": "main", "label": "Medium", "folders": ["core/medium"],
                "default": {"*": [{"key": "core/medium_amateur", "w": 2}, {"key": "core/medium_pro", "w": 1}]}}]},
    {"id": "person", "label": "Person", "people": True, "glue": "It shows a woman in her …, ….",
     "slots": [{"id": "age", "label": "Age", "folders": ["person/age"], "default": {"*": _p("person/age_band")}},
               {"id": "ethnicity", "label": "Ethnicity", "folders": ["person/ethnicity"],
                "default": {"*": _p("person/ethnicity")}}]},
    {"id": "expression", "label": "Expression + mood", "people": True,
     "glue": "Her expression is … and her gaze is …. The mood is …",
     "opts": {"family": "full", "candid": False, "gaze": True},
     "slots": [{"id": "mood", "label": "Mood", "folders": ["core/mood"], "default": {"*": _p("core/mood")}},
               {"id": "gaze", "label": "Gaze", "folders": ["person/gaze"], "default": {"*": _p("person/gaze")}}]},
    {"id": "hair", "label": "Hair + face", "people": True, "glue": "Her hair is …. (+ face details)",
     "opts": {"details": ["eyes", "nose", "lips", "face_marks"], "range": "1-2"},
     "slots": [{"id": "hair", "label": "Hair", "folders": ["person/hair", "man/hair"],
                "default": {"woman": _p("person/hair"), "man": _p("man/hair")}}]},
    {"id": "clothing", "label": "Clothing", "people": True, "glue": "She is wearing ….",
     "slots": [{"id": "main", "label": "Clothing", "folders": ["clothing/"],
                "default": {"woman": _p("clothing/everyday"), "man": _p("clothing/menswear")}}]},
    {"id": "pose", "label": "Pose or scene bundle", "people": True, "glue": "She is posed …. / She is … (scene)",
     "opts": {"mode": "pose"},
     "slots": [{"id": "main", "label": "Pose", "folders": ["pose/"], "default": {"*": _p("pose/neutral")}}]},
    {"id": "place", "label": "Place", "people": False, "glue": "The scene is ….",
     "slots": [{"id": "main", "label": "Place", "folders": ["core/place_"],
                "default": {"*": _p("core/place_indoor")}}]},
    {"id": "light", "label": "Light", "people": False, "glue": "….",
     "slots": [{"id": "main", "label": "Light", "folders": ["core/light_", "core/weather"],
                "default": {"*": _p("core/light_daylight")}}]},
    {"id": "shot", "label": "Shot + camera angle", "people": False, "glue": "This is …, shot ….",
     "opts": {"angle": True},
     "slots": [{"id": "shot", "label": "Shot", "folders": ["core/shot_"], "default": {"*": _p("core/shot_fashion")}},
               {"id": "angle", "label": "Camera angle", "folders": ["core/camera_angle"],
                "default": {"*": _p("core/camera_angle_standing")}}]},
    {"id": "realism", "label": "Realism", "people": False, "glue": "….",
     "slots": [{"id": "main", "label": "Realism", "folders": ["core/realism"], "default": {"*": _p("core/realism")}}]},
    {"id": "palette", "label": "Palette", "people": False, "glue": "….",
     "slots": [{"id": "main", "label": "Palette", "folders": ["core/palette"], "default": {"*": _p("core/palette")}}]},
]
BLOCK_IDS = [b["id"] for b in BLOCKS]
_BY_ID = {b["id"]: b for b in BLOCKS}


class BuilderError(ValueError):
    """A user-facing problem with a builder request."""


def is_nsfw(name: str) -> bool:
    """The NSFW rule of the whole pack (wildcards.is_excluded): one rule for hiding and for the checks."""
    from .wildcards import is_excluded

    return is_excluded(name)


# --------------------------------------------------------------------------------------------- spec


def _default_slot(slot: dict, sex: str) -> list[dict]:
    d = slot["default"]
    return copy.deepcopy(d.get(sex) or d.get("*") or d.get("woman") or [])


def default_spec(sex: str = "woman") -> dict:
    """A working starting point: every block on with its default pools."""
    sex = sex if sex in SEXES else "woman"
    blocks = {}
    for b in BLOCKS:
        on = not (b["people"] and sex == "none")
        blocks[b["id"]] = {"on": on, "optional": False, "opts": copy.deepcopy(b.get("opts", {})),
                           "slots": {s["id"]: _default_slot(s, sex) for s in b["slots"]}}
    return {"sex": sex, "blocks": blocks}


def _weight(v) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        n = 1
    return max(1, min(MAX_WEIGHT, n))


def _pools(raw) -> list[dict]:
    """``[{"key", "w"}]`` -> checked list; the same key twice is merged (weights added)."""
    out: list[dict] = []
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, str):
            item = {"key": item}
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip().strip("_").lower()
        if not KEY_RE.match(key):
            raise BuilderError(f"KDX Builder: {key or '(empty)'!r} is not a full pool name like core/medium_pro.")
        w = _weight(item.get("w", 1))
        same = next((p for p in out if p["key"] == key), None)
        if same:
            same["w"] = min(MAX_WEIGHT, same["w"] + w)
        else:
            out.append({"key": key, "w": w})
    if len(out) > MAX_POOLS:
        raise BuilderError(f"KDX Builder: at most {MAX_POOLS} pools in one slot.")
    return out


def normalize_spec(raw) -> dict:
    """Fill defaults and validate (raises BuilderError on a broken pool name)."""
    raw = raw if isinstance(raw, dict) else {}
    sex = raw.get("sex") if raw.get("sex") in SEXES else "woman"
    spec = default_spec(sex)
    rblocks = raw.get("blocks") if isinstance(raw.get("blocks"), dict) else {}
    for b in BLOCKS:
        rb = rblocks.get(b["id"])
        if not isinstance(rb, dict):
            continue
        blk = spec["blocks"][b["id"]]
        blk["on"] = bool(rb.get("on", blk["on"])) and not (b["people"] and sex == "none")
        blk["optional"] = bool(rb.get("optional", False))
        ropts = rb.get("opts") if isinstance(rb.get("opts"), dict) else {}
        for k, v in ropts.items():
            if k in blk["opts"]:
                blk["opts"][k] = v
        rslots = rb.get("slots") if isinstance(rb.get("slots"), dict) else {}
        for s in b["slots"]:
            if s["id"] in rslots:
                blk["slots"][s["id"]] = _pools(rslots[s["id"]])
    e = spec["blocks"]["expression"]["opts"]
    e["family"] = e["family"] if e["family"] in ("full", "soft") else "full"
    e["candid"], e["gaze"] = bool(e["candid"]), bool(e["gaze"])
    h = spec["blocks"]["hair"]["opts"]
    h["details"] = [d for d in DETAIL_IDS if d in (h["details"] if isinstance(h["details"], list) else [])]
    h["range"] = str(h["range"]).strip() if RANGE_RE.match(str(h["range"]).strip()) else "1-2"
    p = spec["blocks"]["pose"]["opts"]
    p["mode"] = p["mode"] if p["mode"] in ("pose", "scene") else "pose"
    spec["blocks"]["shot"]["opts"]["angle"] = bool(spec["blocks"]["shot"]["opts"]["angle"])
    return spec


# --------------------------------------------------------------------------------------------- compose


def _choice(pools: list[dict], prefix=None) -> str:
    """``[{key, w}]`` -> ``{2::__a__|__b__}``; ``prefix(key)`` puts a lead word before a token."""
    opts = []
    for p in pools:
        lead = prefix(p["key"]) if prefix else ""
        opts.append(f"{p['w']}::" if p["w"] != 1 else "")
        opts[-1] += f"{lead}__{p['key']}__"
    return "{" + "|".join(opts) + "}"


def _pose_lead(key: str) -> str:
    return "" if POSE_IS_RE.match(key) or "_scene" in key else "posed "


def _scene_skips(spec: dict) -> set[str]:
    """Blocks a scene bundle already contains (place and shot; light too for pose/lying_scene only)."""
    pose = spec["blocks"]["pose"]
    if not pose["on"] or pose["opts"]["mode"] != "scene" or spec["sex"] == "none":
        return set()
    keys = [p["key"] for p in pose["slots"]["main"]]
    skip = {"place", "shot"}
    if keys and all(k == LYING_SCENE for k in keys):
        skip.add("light")
    return skip


def _detail_text(did: str, pr: dict) -> str:
    glue = next(g for i, _lbl, g in DETAILS if i == did)
    return glue.format(**pr)


def render_block(bid: str, blk: dict, sex: str, choice=None) -> str:
    """One block as text (without the optional wrapper). Raises BuilderError when a slot is empty.
    ``choice(pools, prefix=None)`` renders a slot (default :func:`_choice`; the parser passes a marker)."""
    choice = choice or _choice
    b = _BY_ID[bid]
    for s in b["slots"]:
        needed = not (bid == "expression" and s["id"] == "gaze" and not blk["opts"]["gaze"]) and \
            not (bid == "shot" and s["id"] == "angle" and not blk["opts"]["angle"])
        if needed and not blk["slots"][s["id"]]:
            raise BuilderError(f"KDX Builder: {b['label']} › {s['label']} has no pool.")
    pr = PRONOUNS.get(sex, {"Subj": "It", "Poss": "Its", "poss": "its", "noun": "a person"})
    sl, o = blk["slots"], blk["opts"]
    if bid == "medium":
        return f"The image is {choice(sl['main'])}."
    if bid == "person":
        return f"It shows {pr['noun']} in {pr['poss']} {choice(sl['age'])}, {choice(sl['ethnicity'])}."
    if bid == "expression":
        def expr(fam):
            if o["candid"] and fam != "soft":
                return "{2::__%s__|1::__%s__}" % (EXPRESSION[fam], EXPRESSION["candid"])
            return "{__%s__}" % EXPRESSION[fam]

        def clause(fam, mood):
            gaze = f" and {pr['poss']} gaze is {choice(sl['gaze'])}" if o["gaze"] else ""
            return f"{pr['Poss']} expression is {expr(fam)}{gaze}. The mood is {mood}"

        mood = choice(sl["mood"])
        if o["family"] == "soft":
            return clause("soft", mood) + "."
        return ("{5::" + clause("positive", mood) + "|3::" + clause("neutral", mood) + "|2::"
                + clause("negative", "{__%s__}" % SOMBER) + "}.")
    if bid == "hair":
        out = f"{pr['Poss']} hair is {choice(sl['hair'])}."
        if o["details"]:
            out += " {" + o["range"] + "$$ $$" + "|".join(_detail_text(d, pr) for d in o["details"]) + "}"
        return out
    if bid == "clothing":
        return f"{pr['Subj']} is wearing {choice(sl['main'])}."
    if bid == "pose":
        pools = sl["main"]
        if o["mode"] == "scene":
            return f"{pr['Subj']} is {choice(pools)}."
        leads = {_pose_lead(p["key"]) for p in pools}
        if len(leads) == 1:
            return f"{pr['Subj']} is {leads.pop()}{choice(pools)}."
        return f"{pr['Subj']} is {choice(pools, _pose_lead)}."
    if bid == "place":
        return f"The scene is {choice(sl['main'])}."
    if bid == "shot":
        angle = f", shot {choice(sl['angle'])}" if o["angle"] else ""
        return f"This is {choice(sl['shot'])}{angle}."
    return f"{choice(sl['main'])}."  # light, realism, palette


def active_blocks(spec: dict) -> list[str]:
    skip = _scene_skips(spec)
    return [b["id"] for b in BLOCKS if spec["blocks"][b["id"]]["on"] and b["id"] not in skip
            and not (b["people"] and spec["sex"] == "none")]


def compose(spec: dict) -> str:
    """Spec -> one-line template. Optional blocks become ``{text |}`` (a run at the start) or ``{ text|}``,
    so the line never gets a double space."""
    spec = normalize_spec(spec)
    ids = active_blocks(spec)
    if not ids:
        raise BuilderError("KDX Builder: switch on at least one block.")
    out = ""
    prev = None  # None (start) | "trail" ({text |}) | "lead" ({ text|}) | "plain"
    for bid in ids:
        blk = spec["blocks"][bid]
        text = render_block(bid, blk, spec["sex"])
        if blk["optional"]:
            if prev in (None, "trail"):  # the run of optional blocks at the start carries its space after
                out += "{" + text + " |}"
                prev = "trail"
            else:
                out += "{ " + text + "|}"
                prev = "lead"
            continue
        if prev in ("lead", "plain"):
            out += " "
        out += text
        prev = "plain"
    return out


# --------------------------------------------------------------------------------------------- bubbles (AST)
#
# The canvas edits a template as a tree of bubbles; the line is only ever written by serialize():
#   {"t": "text", "v": "She is "}           literal text ({ } and, inside a group, | are escaped on output)
#   {"t": "pool", "name": "core/light_sky"}  a __name__ token
#   {"t": "choice", "opts": [{"w": "3", "items": [...]}, ...], "count": None | "1-2", "sep": None | " "}
#        one of the options ({a|b}, weights N::); an empty option makes it "sometimes" ({a|});
#        count = multi-pick ({1-2$$ $$a|b}); sep None = the engine's default ", "
#   {"t": "raw", "v": "{"}                  text kept exactly as written (an unbalanced brace)

_W_RE = re.compile(r"^(\d+(?:\.\d+)?|\.\d+)::")
_COUNT_RE = re.compile(r"^\s*(\d*)\s*(?:-\s*(\d*))?\s*$")
_POOL_NAME_RE = re.compile(r"^[\w.\-+/*\\ ]+$")
_ESC = "{}|"
MAX_NODES = 5000
MAX_DEPTH = 24


def _close(s: str, i: int) -> int:
    """Index after the ``}`` matching the ``{`` at ``s[i]`` (escapes skipped); -1 when unbalanced."""
    depth, j = 0, i
    while j < len(s):
        c = s[j]
        if c == "\\" and j + 1 < len(s) and s[j + 1] in _ESC:
            j += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1
    return -1


def _split(body: str, sep: str) -> list[str]:
    """Split at ``sep`` outside nested braces and escapes."""
    parts, depth, cur, j = [], 0, "", 0
    while j < len(body):
        c = body[j]
        if c == "\\" and j + 1 < len(body) and body[j + 1] in _ESC:
            cur += body[j:j + 2]
            j += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        if depth == 0 and body.startswith(sep, j):
            parts.append(cur)
            cur = ""
            j += len(sep)
            continue
        cur += c
        j += 1
    parts.append(cur)
    return parts


def _add_text(nodes: list, text: str) -> None:
    if not text:
        return
    if nodes and nodes[-1]["t"] == "text":
        nodes[-1]["v"] += text
    else:
        nodes.append({"t": "text", "v": text})


def _lane(s: str, depth: int) -> list[dict]:
    if depth > MAX_DEPTH:
        return [{"t": "raw", "v": s}] if s else []
    nodes: list[dict] = []
    i = 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s) and s[i + 1] in _ESC:
            _add_text(nodes, s[i + 1])
            i += 2
        elif c == "{":
            j = _close(s, i)
            if j < 0:
                nodes.append({"t": "raw", "v": "{"})
                i += 1
            else:
                nodes.append(_group(s[i + 1:j - 1], depth + 1))
                i = j
        elif c == "}":
            nodes.append({"t": "raw", "v": "}"})
            i += 1
        elif s.startswith("__", i) and TOKEN_RE.match(s, i):
            m = TOKEN_RE.match(s, i)
            nodes.append({"t": "pool", "name": m.group(1)})
            i = m.end()
        else:
            _add_text(nodes, c)
            i += 1
    return nodes


def _group(body: str, depth: int) -> dict:
    count = sep = None
    rest = body
    parts = _split(body, "$$")
    if len(parts) >= 3 and _COUNT_RE.match(parts[0]):
        count, sep, rest = parts[0], parts[1], "$$".join(parts[2:])
    elif len(parts) >= 2 and _COUNT_RE.match(parts[0]):
        count, rest = parts[0], "$$".join(parts[1:])
    opts = []
    for opt in _split(rest, "|"):
        m = _W_RE.match(opt)
        opts.append({"w": m.group(1) if m else None, "items": _lane(opt[m.end():] if m else opt, depth)})
    return {"t": "choice", "opts": opts, "count": count, "sep": sep}


def parse_line(text: str) -> list[dict]:
    """A template line -> bubbles. ``serialize(parse_line(t)) == t`` for the lines of a real library."""
    return _lane(str(text or ""), 0)


def _esc_text(v: str, in_group: bool) -> str:
    v = v.replace("{", "\\{").replace("}", "\\}")
    return v.replace("|", "\\|") if in_group else v


def serialize(nodes: list[dict], in_group: bool = False) -> str:
    """Bubbles -> template line."""
    out = []
    for n in nodes:
        t = n["t"]
        if t == "text":
            out.append(_esc_text(n["v"], in_group))
        elif t == "raw":
            out.append(n["v"])
        elif t == "pool":
            out.append(f"__{n['name']}__")
        else:
            head = ""
            if n.get("count") is not None:
                head = n["count"] + "$$" + (n["sep"] + "$$" if n.get("sep") is not None else "")
            opts = [(f"{o['w']}::" if o.get("w") else "") + serialize(o["items"], True) for o in n["opts"]]
            out.append("{" + head + "|".join(opts) + "}")
    return "".join(out)


def normalize_nodes(raw, _depth: int = 0, _count: list | None = None) -> list[dict]:
    """Validate bubbles sent by the panel (raises BuilderError); unknown keys are dropped."""
    _count = _count if _count is not None else [0]
    if _depth > MAX_DEPTH:
        raise BuilderError("KDX Builder: groups are nested too deep.")
    if not isinstance(raw, list):
        raise BuilderError("KDX Builder: expected a list of bubbles.")
    out: list[dict] = []
    for n in raw:
        _count[0] += 1
        if _count[0] > MAX_NODES:
            raise BuilderError("KDX Builder: too many bubbles.")
        t = n.get("t") if isinstance(n, dict) else None
        if t in ("text", "raw"):
            v = str(n.get("v") or "")
            if "\n" in v or "\r" in v:
                raise BuilderError("KDX Builder: a template is one line (no line breaks in text).")
            if v:
                out.append({"t": t, "v": v})
        elif t == "pool":
            name = str(n.get("name") or "").strip()
            if not _POOL_NAME_RE.match(name) or "__" in name:
                raise BuilderError(f"KDX Builder: {name!r} is not a pool name.")
            out.append({"t": "pool", "name": name})
        elif t == "choice":
            opts = n.get("opts")
            if not isinstance(opts, list) or not opts:
                raise BuilderError("KDX Builder: a group needs at least one option.")
            count, sep = n.get("count"), n.get("sep")
            if count is not None and not _COUNT_RE.match(str(count)):
                raise BuilderError(f"KDX Builder: {count!r} is not a count like 2 or 1-3.")
            if sep is not None and any(c in str(sep) for c in "{}|$\n"):
                raise BuilderError("KDX Builder: the separator cannot contain { } | $.")
            clean = []
            for o in opts:
                o = o if isinstance(o, dict) else {}
                w = o.get("w")
                w = None if w is None or w == "" else str(w)
                if w is not None and not _W_RE.match(w + "::"):
                    raise BuilderError(f"KDX Builder: {w!r} is not a weight.")
                clean.append({"w": w, "items": normalize_nodes(o.get("items") or [], _depth + 1, _count)})
            out.append({"t": "choice", "opts": clean, "count": None if count is None else str(count),
                        "sep": None if sep is None else str(sep)})
        else:
            raise BuilderError(f"KDX Builder: unknown bubble type {t!r}.")
    return out


_VARIANTS = [("expression", "Expression + mood (soft)", {"family": "soft"}),
             ("hair", "Hair (no face details)", {"details": []}),
             ("pose", "Scene bundle", {"mode": "scene"}),
             ("shot", "Shot (no angle)", {"angle": False})]


def snippets() -> dict[str, list[dict]]:
    """Ready sentences for the palette, per sex: every block with its default pools, plus a few variants."""
    out: dict[str, list[dict]] = {}
    for sex in SEXES:
        spec = default_spec(sex)
        items = []
        for b in BLOCKS:
            if b["people"] and sex == "none":
                continue
            blk = spec["blocks"][b["id"]]
            items.append({"id": b["id"], "label": b["label"], "nodes": parse_line(render_block(b["id"], blk, sex))})
            for bid, label, opts in _VARIANTS:
                if bid != b["id"]:
                    continue
                v = copy.deepcopy(blk)
                v["opts"].update(opts)
                if bid == "pose":
                    v["slots"]["main"] = [{"key": "pose/studio_scene", "w": 1}]
                items.append({"id": f"{bid}_{next(iter(opts))}", "label": label,
                              "nodes": parse_line(render_block(bid, v, sex))})
        out[sex] = items
    return out


def starter(sex: str = "woman") -> list[dict]:
    """The bubbles of a new template: every block with its default pools, joined by spaces."""
    return parse_line(compose(default_spec(sex)))


# --------------------------------------------------------------------------------------------- checks


def _tokens(text: str) -> list[str]:
    return [m.group(1) for m in TOKEN_RE.finditer(text)]


def _w(level: str, code: str, msg: str) -> dict:
    return {"level": level, "code": code, "msg": msg}


def check(text: str, lib: Library, name: str = "", samples: int = 200, seed: int = 0) -> list[dict]:
    """Rule checks before saving: ``[{"level": "error"|"warn", "code", "msg"}]`` (empty = fine)."""
    out: list[dict] = []
    text = str(text or "")
    if not text.strip():
        return [_w("error", "empty", "The template is empty.")]
    if "\n" in text or "\r" in text:
        out.append(_w("error", "one_line", "A template is one line: a second line becomes a random alternative."))
    if "  " in text:
        out.append(_w("warn", "spaces", "Double space in the template."))
    toks = _tokens(text)
    for t in sorted(set(toks)):
        if "/" not in t or "*" in t:
            out.append(_w("warn", "full_token",
                          f"__{t}__ is not a full __folder/file__ token: it pools every file of that name."))
        elif lib.data and t.lower() not in lib.data:
            out.append(_w("error", "unknown", f"__{t}__: no such pool in the library."))
    keys = {t.lower() for t in toks}
    expr = [k for k in keys if k.startswith("person/expression_")]
    if expr and not any(k.startswith("core/mood") for k in keys):
        out.append(_w("warn", "mood", "person/expression_* is used without a mood (core/mood…): pick them together."))
    nsfw = is_nsfw(name)
    if nsfw and any(k in keys for k in (EXPRESSION["positive"], EXPRESSION["negative"])):
        out.append(_w("warn", "soft", "NSFW templates use person/expression_soft (no negative family)."))
    places = {k for k in keys if k.startswith("core/place_")} | (keys & INDOOR_SCENES)
    if SKY_LIGHT in keys and places - OUTDOOR_PLACES:
        out.append(_w("warn", "sky", "core/light_sky is for places that are always outdoors, not "
                      + ", ".join(sorted(places - OUTDOOR_PLACES)) + " (fine only in separate branches)."))
    he, she = re.search(r"\b(He|His|a man in his)\b", text), re.search(r"\b(She|Her|a woman in her)\b", text)
    if name.endswith("_woman") and he or name.endswith("_man") and she:
        out.append(_w("warn", "sex_name", "One template per sex: the name and the pronouns of the text disagree."))
    if nsfw and any(k.startswith("clothing/") for k in keys):
        out.append(_w("warn", "clothing", "NSFW template with a clothing pool (sheer templates are a deliberate "
                      "exception)."))
    if lib.data and not any(e["level"] == "error" for e in out):
        rng = random.Random(seed)
        ratio_bad, cloth, missing = 0, 0, set()
        for _ in range(samples):
            res = lib.expand(text, rng.randrange(2**31))
            missing.update(res.missing)
            if len(RATIO_RE.findall(res.text)) != 1:
                ratio_bad += 1
            if nsfw and CLOTHING_RE.search(res.text):
                cloth += 1
        if ratio_bad:
            out.append(_w("warn", "ratio", f"{ratio_bad * 100 // samples or 1} % of {samples} expansions do not "
                          "contain exactly one shot with an aspect ratio N:N."))
        if cloth:
            out.append(_w("warn", "clothing_words", f"NSFW name, but {cloth * 100 // samples or 1} % of {samples} "
                          "expansions contain a clothing word."))
        if missing:
            out.append(_w("error", "missing", "Unknown wildcards left after expanding: " + ", ".join(sorted(missing))))
    return out


# --------------------------------------------------------------------------------------------- library views


def pool_head(path: str | None) -> list[str]:
    """The comment lines at the top of a pool file (its description)."""
    out: list[str] = []
    if not path:
        return out
    try:
        with open(path, encoding="utf-8-sig", errors="replace") as f:
            for line in f:
                s = line.strip()
                if not s:
                    continue
                if not s.startswith("#"):
                    break
                out.append(s.lstrip("#").strip())
    except OSError:
        pass
    return out


def raw_text(lib: Library, key: str) -> str:
    """The value lines of a library file joined by newlines (templates: their one line)."""
    return "\n".join(e.value if e.weight == 1 else f"{_fmt_w(e.weight)}::{e.value}" for e in lib.data.get(key, []))


def _fmt_w(w: float) -> str:
    return str(int(w)) if float(w).is_integer() else str(w)


_usage_cache: dict = {"lib": None, "data": None}


def usage(lib: Library) -> dict[str, dict[str, list[str]]]:
    """``pool -> {"templates": [...], "pools": [...]}``: who reads it, through full, short or glob tokens."""
    if _usage_cache["lib"] is lib:
        return _usage_cache["data"]
    out: dict[str, dict[str, list[str]]] = {}
    for key, entries in lib.data.items():
        refs = set()
        for e in entries:
            for t in _tokens(e.value):
                refs.update(lib.match_keys(t))
        for r in refs:
            if r == key:
                continue
            slot = out.setdefault(r, {"templates": [], "pools": []})
            if key.startswith("templates/"):
                slot["templates"].append(key[len("templates/"):])
            else:
                slot["pools"].append(key)
    for v in out.values():
        v["templates"].sort()
        v["pools"].sort()
    _usage_cache.update(lib=lib, data=out)
    return out


_index_cache: dict = {"lib": None, "data": None}


def pool_index(lib: Library) -> list[dict]:
    """Every pool (templates left out): key, number of values, description, who uses it. Cached per library."""
    if _index_cache["lib"] is lib:
        return _index_cache["data"]
    use = usage(lib)
    data = []
    for key in lib.keys():
        if key.startswith("templates/"):
            continue
        u = use.get(key, {"templates": [], "pools": []})
        head = pool_head(lib.sources.get(key))
        data.append({"key": key, "count": len(lib.data[key]), "desc": head[0] if head else "",
                     "templates": u["templates"], "pools": u["pools"]})
    _index_cache.update(lib=lib, data=data)
    return data


def pool_detail(lib: Library, key: str, hide=None) -> dict:
    key = str(key or "").strip().strip("_").lower()
    if key not in lib.data or key.startswith("templates/"):
        raise BuilderError(f"KDX Builder: no pool {key!r}.")
    u = usage(lib).get(key, {"templates": [], "pools": []})
    tpls = [t for t in u["templates"] if not (hide and hide(t))]
    return {"key": key, "count": len(lib.data[key]), "head": pool_head(lib.sources.get(key)),
            "values": [{"value": e.value, "w": e.weight} for e in lib.data[key]],
            "templates": tpls, "hidden_templates": len(u["templates"]) - len(tpls), "pools": u["pools"]}


def preview(text: str, lib: Library, count: int = 3, seed: int | None = None) -> list[dict]:
    """``count`` expansions with random (or given) seeds."""
    rng = random.Random(seed)
    out = []
    for _ in range(max(1, min(int(count), 10))):
        s = rng.randrange(2**31)
        res = lib.expand(text, s)
        out.append({"seed": s, "text": res.text, "missing": res.missing})
    return out


# --------------------------------------------------------------------------------------------- saving


def check_name(name: str) -> str:
    n = str(name or "").strip()
    if n.endswith(".txt"):
        n = n[:-4]
    if not NAME_RE.match(n):
        raise BuilderError("KDX Builder: template names are lower case letters, digits and _ (e.g. lounge_woman).")
    return n


def write_template(folder: str, name: str, text: str, *, overwrite: bool = False) -> dict:
    """Write ``<folder>/templates/<name>.txt`` atomically. An existing file is replaced only with ``overwrite``;
    then it is first copied to ``<name>.txt.bak`` and its leading comment lines are kept.

    Returns ``{"path", "backup", "created"}``; raises FileExistsError when the file exists and not overwrite."""
    name = check_name(name)
    text = str(text).strip()
    if not text or "\n" in text or "\r" in text:
        raise BuilderError("KDX Builder: a template is exactly one non-empty line.")
    tdir = os.path.join(folder, "templates")
    os.makedirs(tdir, exist_ok=True)
    path = os.path.join(tdir, name + ".txt")
    backup = None
    head: list[str] = []
    exists = os.path.exists(path)
    if exists:
        if not overwrite:
            raise FileExistsError(path)
        with open(path, "rb") as f:
            old = f.read()
        backup = path + ".bak"
        _atomic_write(backup, old)
        for line in old.decode("utf-8", "replace").splitlines():
            if line.strip().startswith("#"):
                head.append(line.rstrip())
            elif line.strip():
                break
    _atomic_write(path, ("\n".join(head + [text]) + "\n").encode("utf-8"))
    return {"path": path, "backup": backup, "created": not exists}


def _atomic_write(path: str, data: bytes) -> None:
    fd, tmp = tempfile.mkstemp(prefix=".kdx-", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
