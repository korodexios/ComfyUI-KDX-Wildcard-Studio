"""Pool editor: create and edit wildcard pools, retire values and pools into an archive (pure, no ComfyUI).

A pool is ``<root>/<folder>/<name>.txt``: comment lines at the top (its description), then one value per line,
optionally weighted ``N::value``. The editor works on a small model of the file::

    {"key": "core/light_sky", "desc": "what the pool holds", "lines": [{"v": "soft daylight", "w": "3"},
                                                                        {"c": "a comment kept in place"}]}

Rules that never bend:

* Nothing is deleted. A value that leaves the pool (retired, or rewritten into another text) is appended to
  ``<root>/../wildcards_archive/<folder>/<name>_archive.txt`` with the date in a comment; that folder is outside the
  library, so no engine loads it. A whole pool is retired the same way, and only while nothing reads it.
* Every save first copies the old file to ``<name>.txt.bak`` and writes the new one atomically (tmp + rename).
* Only pools inside a library root: never ``templates/`` (the template builder writes those), never ``packs/``
  (installed packs keep their checksums), never a path that leaves the root.
* Words that put a minor in the picture, or an age under 18, block the save (the same rule as packs).
"""

from __future__ import annotations

import datetime as _dt
import os
import random
import re

from . import builder
from .packs import _braces_ok, _minor
from .wildcard_engine import PACKS_DIR, Library, normalize_key, parse_lines
from .wildcards import is_excluded

ARCHIVE_DIR = "wildcards_archive"
RESERVED = ("templates", PACKS_DIR)
SEG_RE = re.compile(r"^[a-z0-9][a-z0-9_]{0,63}$")
FOLDER_SEG_RE = re.compile(r"^[a-z0-9][a-z0-9_\-]{0,63}$")
WEIGHT_RE = re.compile(r"^(\d+(?:\.\d+)?|\.\d+)$")
LEAD_WEIGHT_RE = re.compile(r"^\s*(\d+(?:\.\d+)?|\.\d+)::")
MAX_LINES = 5000
MAX_VALUE = 4000
SAMPLES = 3


class PoolError(ValueError):
    """A pool request that cannot be done; the message says why."""


class PoolInUse(PoolError):
    """Retiring a pool that templates or pools still read."""

    def __init__(self, msg: str, users: dict):
        super().__init__(msg)
        self.users = users


def _w(level: str, code: str, msg: str) -> dict:
    return {"level": level, "code": code, "msg": msg}


# --------------------------------------------------------------------------------------------- keys and paths


def check_key(key: str, *, new: bool = False) -> str:
    """``core/light_sky`` -> normalized key; raises PoolError for templates/, packs/, odd names or ``..``."""
    k = str(key or "").strip().strip("_").replace("\\", "/").lower()
    if k.endswith(".txt"):
        k = k[:-4]
    parts = k.split("/")
    if len(parts) < 2:
        raise PoolError("KDX Pools: a pool lives in a folder: folder/name (e.g. core/light_sky).")
    if parts[0] in RESERVED:
        raise PoolError(f"KDX Pools: {parts[0]}/ is not edited here "
                        + ("(templates are written by the template builder)." if parts[0] == "templates"
                           else "(installed packs keep their checksums; edit the pack before sharing it)."))
    if not all(FOLDER_SEG_RE.match(p) for p in parts[:-1]):
        raise PoolError("KDX Pools: folder names are lower case letters, digits, _ and -.")
    if not (SEG_RE if new else FOLDER_SEG_RE).match(parts[-1]):
        raise PoolError("KDX Pools: pool names are lower case letters, digits and _ (e.g. light_window).")
    return k


def _inside(root: str, path: str) -> str:
    real_root, real = os.path.realpath(root), os.path.realpath(path)
    if os.path.commonpath([real_root, real]) != real_root or real == real_root:
        raise PoolError("KDX Pools: refusing a path outside the wildcard library.")
    return path


def pool_path(roots: list[str], lib: Library, key: str, *, new: bool = False) -> tuple[str, str]:
    """``(root, path)`` of a pool: its current file, or for a new pool a free path in the first root."""
    key = check_key(key, new=new)
    roots = [os.path.abspath(r) for r in roots if os.path.isdir(r)]
    if not roots:
        raise PoolError("KDX Pools: no wildcard folder. Set the wildcard folders in the panel.")
    if new:
        for r in roots:
            if os.path.exists(os.path.join(r, *key.split("/")) + ".txt"):
                raise PoolError(f"KDX Pools: {key} exists already; open it to edit it.")
        if key in lib.data:
            raise PoolError(f"KDX Pools: {key} exists already; open it to edit it.")
        root = roots[0]
        return root, _inside(root, os.path.join(root, *key.split("/")) + ".txt")
    src = lib.sources.get(key)
    if not src:
        raise PoolError(f"KDX Pools: no pool {key}.")
    root = next((r for r in roots if os.path.commonpath([os.path.realpath(r), os.path.realpath(src)])
                 == os.path.realpath(r)), None)
    if root is None:
        raise PoolError("KDX Pools: that pool is not inside a wildcard folder.")
    return root, _inside(root, src)


def archive_path(root: str, key: str) -> str:
    """``<root>/../wildcards_archive/<folder>/<name>_archive.txt``: outside the library, never loaded."""
    folder, name = key.rsplit("/", 1)
    parent = os.path.dirname(os.path.abspath(root).rstrip(os.sep))
    return os.path.join(parent, ARCHIVE_DIR, *folder.split("/"), f"{name}_archive.txt")


# --------------------------------------------------------------------------------------------- file model


def read_model(path: str, key: str) -> dict:
    """The file as ``{key, desc, lines}``: leading comments are the description; later comments stay in place."""
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        raw = f.read().replace("\r\n", "\n").replace("\r", "\n").split("\n")
    desc: list[str] = []
    lines: list[dict] = []
    head = True
    for ln in raw:
        s = ln.strip()
        if not s:
            continue
        if s.startswith("#"):
            if head:
                desc.append(s[1:].strip())
            else:  # a comment between values is kept exactly as written
                lines.append({"c": s[1:]})
            continue
        head = False
        m = LEAD_WEIGHT_RE.match(s)
        lines.append({"v": s[m.end():].strip() if m else s, "w": m.group(1) if m else None})
    return {"key": key, "desc": "\n".join(desc), "lines": lines}


def normalize_model(raw) -> dict:
    """Validate what the panel sends (raises PoolError)."""
    if not isinstance(raw, dict):
        raise PoolError("KDX Pools: expected an object.")
    desc = str(raw.get("desc") or "").replace("\r", "")
    lines_in = raw.get("lines")
    if not isinstance(lines_in, list):
        raise PoolError("KDX Pools: expected a list of lines.")
    if len(lines_in) > MAX_LINES:
        raise PoolError(f"KDX Pools: at most {MAX_LINES} lines.")
    lines: list[dict] = []
    for ln in lines_in:
        if not isinstance(ln, dict):
            raise PoolError("KDX Pools: every line is an object.")
        if "c" in ln:
            c = str(ln.get("c") or "").replace("\n", " ").rstrip()
            if c:
                lines.append({"c": c})
            continue
        v = str(ln.get("v") if ln.get("v") is not None else "")
        if "\n" in v or "\r" in v:
            raise PoolError("KDX Pools: a value is one line.")
        w = ln.get("w")
        w = None if w in (None, "", "1") else str(w).strip()
        lines.append({"v": v, "w": w})
    return {"key": str(raw.get("key") or ""), "desc": desc, "lines": lines}


def to_text(model: dict) -> str:
    out = [f"# {d.strip()}" if d.strip() else "#" for d in model["desc"].split("\n") if model["desc"].strip()]
    for ln in model["lines"]:
        if "c" in ln:
            out.append(f"#{ln['c']}")
        else:
            out.append((f"{ln['w']}::" if ln.get("w") else "") + ln["v"].strip())
    return "\n".join(out) + "\n"


def _values(model: dict) -> list[str]:
    return [ln["v"].strip() for ln in model["lines"] if "c" not in ln]


# --------------------------------------------------------------------------------------------- users


def users(lib: Library, key: str) -> dict:
    """Who reads the pool: templates and pools directly, and the templates that reach it through other pools."""
    use = builder.usage(lib)
    direct = use.get(key, {"templates": [], "pools": []})
    reach, seen, todo = set(direct["templates"]), {key}, list(direct["pools"])
    while todo:
        p = todo.pop()
        if p in seen:
            continue
        seen.add(p)
        u = use.get(p, {"templates": [], "pools": []})
        reach.update(u["templates"])
        todo.extend(u["pools"])
    return {"templates": list(direct["templates"]), "pools": list(direct["pools"]), "reach": sorted(reach)}


def _with(lib: Library, key: str, model: dict) -> Library:
    """The library as it would be with the edited pool."""
    data = dict(lib.data)
    data[key] = parse_lines(to_text(model).split("\n"))
    out = Library(data, dict(lib.sources))
    return out


# --------------------------------------------------------------------------------------------- checks


def check(lib: Library, key: str, model: dict) -> list[dict]:
    """Rule checks before saving: ``[{"level": "error"|"warn", "code", "msg"}]``. Errors block the save."""
    out: list[dict] = []
    vals = [ln for ln in model["lines"] if "c" not in ln]
    if not vals:
        return [_w("error", "empty", "A pool needs at least one value (an empty pool picks nothing).")]
    scene = "scene" in key.rsplit("/", 1)[-1]
    seen: dict[str, int] = {}
    edited = _with(lib, key, model)
    reported: set[str] = set()
    nsfw_users = [t for t in users(lib, key)["reach"] if is_excluded(t) and not t.lower().startswith("sheer")] \
        if key in lib.data else []
    for i, ln in enumerate(vals, 1):
        v, w = ln["v"], ln.get("w")
        at = f"value {i}"
        s = v.strip()
        if not s:
            out.append(_w("error", "blank", f"{at} is empty."))
            continue
        if len(s) > MAX_VALUE:
            out.append(_w("error", "long", f"{at} is longer than {MAX_VALUE} characters."))
        if w is not None and not WEIGHT_RE.match(w):
            out.append(_w("error", "weight", f"{at}: {w!r} is not a weight (a number like 3 or 0.5)."))
        if LEAD_WEIGHT_RE.match(s):
            out.append(_w("error", "weight", f"{at} starts with a second weight: {s[:50]!r}."))
        if not _braces_ok(s):
            out.append(_w("error", "braces", f"{at}: a {{ or }} without its partner: {s[:50]!r}."))
        word = _minor(s)
        if word:
            out.append(_w("error", "minor", f"{at}: {word!r}. The library describes adults only, never a minor or an "
                          "age under 18."))
        if s.endswith(".") and not scene:
            out.append(_w("warn", "full_stop", f"{at} ends with a full stop; the template writes the punctuation."))
        if "  " in s:
            out.append(_w("warn", "spaces", f"{at} has a double space."))
        if v != s:
            out.append(_w("warn", "edge_space", f"{at} starts or ends with a space (it is trimmed on save)."))
        low = s.lower()
        if low in seen:
            out.append(_w("warn", "duplicate", f"{at} repeats value {seen[low]}; use a weight instead."))
        else:
            seen[low] = i
        if nsfw_users and builder.CLOTHING_RE.search(s):
            out.append(_w("warn", "clothing", f"{at} names clothing ({builder.CLOTHING_RE.search(s).group(0)!r}) "
                          "and the pool is used by an NSFW template."))
        for tok in builder.TOKEN_RE.findall(s):
            k = normalize_key(tok)
            if k in reported:
                continue
            reported.add(k)
            if k == key:
                out.append(_w("error", "self", f"__{tok}__ points at the pool itself."))
            elif not edited.match_keys(k):
                out.append(_w("error", "unknown", f"__{tok}__: no such pool in the library."))
            elif "/" not in k or "*" in k:
                out.append(_w("warn", "full_token", f"__{tok}__ is not a full __folder/file__ token."))
    return out


def samples(lib: Library, key: str, model: dict, *, hide=None, count: int = SAMPLES, seed: int | None = None) -> dict:
    """Three prompts with the edited pool: from a template that reads it (a visible one first), else the pool."""
    edited = _with(lib, key, model)
    reach = users(lib, key)["reach"] if key in lib.data else []
    visible = [t for t in reach if not (hide and hide(t))]
    rng = random.Random(seed)
    tpl = rng.choice(visible) if visible else None
    text = f"__templates/{tpl}__" if tpl else f"__{key}__"
    out = []
    for _ in range(count):
        s = rng.randrange(2**31)
        res = edited.expand(text, s)
        out.append({"seed": s, "text": res.text, "missing": res.missing})
    return {"template": tpl, "samples": out}


# --------------------------------------------------------------------------------------------- writing


def _today() -> str:
    return _dt.date.today().isoformat()


def _append_archive(root: str, key: str, header: str, lines: list[str]) -> str:
    path = archive_path(root, key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    old = ""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            old = f.read()
        if old and not old.endswith("\n"):
            old += "\n"
    builder._atomic_write(path, (old + f"# {header}\n" + "\n".join(lines) + "\n").encode("utf-8"))
    return path


def save(roots: list[str], lib: Library, key: str, model: dict, *, new: bool = False) -> dict:
    """Write the pool. Raises PoolError on an error-level check. Values that left the pool are archived.

    Returns ``{"key", "path", "created", "backup", "archived": n, "archive"}``."""
    key = check_key(key, new=new)
    model = normalize_model(model)
    errors = [w for w in check(lib, key, model) if w["level"] == "error"]
    if errors:
        raise PoolError("KDX Pools: not saved: " + " ".join(e["msg"] for e in errors[:5]))
    root, path = pool_path(roots, lib, key, new=new)
    for ln in model["lines"]:
        if "c" not in ln:
            ln["v"] = ln["v"].strip()
    text = to_text(model)
    backup = None
    archived: list[str] = []
    if not new:
        with open(path, "rb") as f:
            old_bytes = f.read()
        backup = path + ".bak"
        builder._atomic_write(backup, old_bytes)
        old = read_model(path, key)
        keep = set(_values(model))
        archived = [(f"{ln['w']}::" if ln.get("w") else "") + ln["v"] for ln in old["lines"]
                    if "c" not in ln and ln["v"] not in keep]
    else:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    archive = _append_archive(root, key, f"retired from {key} on {_today()} (KDX template builder)", archived) \
        if archived else None
    if new and os.path.exists(path):  # appeared meanwhile: never overwrite
        raise PoolError(f"KDX Pools: {key} exists already.")
    builder._atomic_write(path, text.encode("utf-8"))
    return {"key": key, "path": path, "created": new, "backup": bool(backup), "archived": len(archived),
            "archive": archive}


def retire(roots: list[str], lib: Library, key: str) -> dict:
    """Move a whole pool into the archive. Refused (PoolInUse) while any template or pool reads it."""
    key = check_key(key)
    u = users(lib, key)
    if u["templates"] or u["pools"]:
        raise PoolInUse(f"KDX Pools: {key} is still used by {len(u['templates'])} template(s) and "
                        f"{len(u['pools'])} pool(s); take it out of them first.", u)
    root, path = pool_path(roots, lib, key)
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        body = [ln.rstrip("\n") for ln in f if ln.strip()]
    archive = _append_archive(root, key, f"whole pool {key} retired on {_today()} (KDX template builder)", body)
    with open(path, "rb") as f:
        builder._atomic_write(path + ".bak", f.read())  # one more copy next to it (never loaded)
    os.remove(path)  # the archive holds every line now: the pool only leaves the library
    return {"key": key, "archive": archive, "lines": len(body)}
