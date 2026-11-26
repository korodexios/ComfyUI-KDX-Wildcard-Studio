"""Wildcard packs: share templates together with every pool they need, as one ``.zip`` (pure, no ComfyUI).

A pack is a small wildcard library in a zip::

    pack.json                      name, title, author, version, description, license, nsfw, templates, files (md5)
    templates/<name>.txt           the templates (one line each)
    <folder>/<pool>.txt            every pool the templates reach, recursively through the tokens in the values

Export collects that from the user's library. Import reads a zip as untrusted data: only ``.txt`` files and
``pack.json``, no paths outside the zip root, no symlinks, size limits, UTF-8 text only, then the same text
rules the library checks use (lint per file + expansions per template). Nothing in a pack is ever run.

Install never touches an existing file. Inside the first wildcard folder::

    packs/<pack>/pack.json         the pack's pack.json + an "installed" record (template names, md5)
    packs/<pack>/<folder>/<pool>.txt
    templates/<pack>_<name>.txt    (nsfw packs: nsfw_<pack>_<name>, so the NSFW switch hides them)

Tokens are rewritten on the way in: ``__core/x__`` -> ``__packs/<pack>/core/x__``, ``__templates/t__`` ->
``__templates/<pack>_t__``. The wildcard engine applies the usual glob / short-name rules inside
``packs/<pack>/`` only and never lets a glob from outside reach into a pack (wildcard_engine.match_keys), so a
pack behaves as it did on its own and changes nothing the rest of the library picks. Uninstall removes the
pack folder and its template files (a template the user edited after installing is kept and reported).
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import io
import json
import os
import random
import re
import shutil
import tempfile
import zipfile

from . import builder
from .wildcard_engine import PACKS_DIR, Library, normalize_key, parse_lines
from .wildcards import is_excluded

FORMAT = 1
BOM = chr(0xFEFF)
MANIFEST = "pack.json"
TEMPLATES = "templates"

MAX_ZIP_BYTES = 8 * 1024 * 1024
MAX_FILE_BYTES = 1024 * 1024
MAX_TOTAL_BYTES = 16 * 1024 * 1024
MAX_FILES = 2000
MAX_TEMPLATES = 200
MAX_DEPTH = 6
MAX_LINE = 4000
SAMPLES = 60  # expansions per template in the struct check

LICENSES = ("CC0-1.0", "CC-BY-4.0", "CC-BY-SA-4.0", "MIT")
DEFAULT_LICENSE = "CC0-1.0"  # the default: anyone may use a shared pack for anything, no credit needed

PACK_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")
VERSION_RE = re.compile(r"^\d{1,4}\.\d{1,4}\.\d{1,4}$")
SEG_RE = re.compile(r"^[a-z0-9][a-z0-9_\-]{0,63}$")
MD5_RE = re.compile(r"^[0-9a-f]{32}$")
TOKEN_RE = re.compile(r"__([\w.\-+/*\\ ]+?)__")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
DOUBLE_WEIGHT_RE = re.compile(r"^\s*(\d+(?:\.\d+)?|\.\d+)::\s*(\d+(?:\.\d+)?|\.\d+)::")
WEIGHT_LEAK_RE = re.compile(r"\d::")
RATIO_RE = builder.RATIO_RE
PUNCT_RE = re.compile(r"\.\.|,,|, \.|\s[,.]")
#: Words that put a minor in the picture (the same list as the library's struct check) and ages under 18.
MINOR_RE = re.compile(
    r"\b(child|children|childlike|girl|girls|boy|boys|kid|kids|school|schoolgirl|schoolboy|teen|teens|teenage|"
    r"teenager|preteen|pre-teen|underage|minors|loli|lolita|shota|toddler|infant|baby-faced|juvenile|"
    r"adolescent|adolescents|puberty|young-looking)\b", re.I)
AGE_RE = re.compile(
    r"\b(?:([1-9]|1[0-7])[- ]?(?:(?:years?|yrs?)[- ]old|y\.?o\.?)|(?:aged?|age of)\s+([1-9]|1[0-7]))(?![\w-])", re.I)


class PackError(ValueError):
    """A pack that cannot be read, exported or installed; the message says why."""


class PackExists(PackError):
    """The pack is installed already (install again with replace)."""


def _msg(level: str, code: str, msg: str, file: str = "") -> dict:
    out = {"level": level, "code": code, "msg": msg}
    if file:
        out["file"] = file
    return out


def md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def _text(s: str) -> str:
    """File text as stored in a pack: ``\\n`` line ends, no BOM, one final newline."""
    s = str(s).replace("\r\n", "\n").replace("\r", "\n").lstrip(BOM)
    return s.rstrip("\n") + "\n" if s.strip() else ""


# ------------------------------------------------------------------------------------------------ paths


def key_of(path: str) -> str:
    """``core/light_sky.txt`` -> ``core/light_sky`` (the path inside the pack is the key)."""
    return path[:-4] if path.endswith(".txt") else path


def template_of(key: str) -> str | None:
    pre = TEMPLATES + "/"
    return key[len(pre):] if key.startswith(pre) else None


def check_path(path: str) -> str | None:
    """Why ``path`` (a .txt file inside a pack) is not allowed, or None. Keys must already be normal: lower case,
    ``[a-z0-9_-]`` segments, at most MAX_DEPTH deep, ``templates/<name>`` one level, ``packs/`` reserved."""
    parts = key_of(path).split("/")
    if len(parts) > MAX_DEPTH:
        return f"{path}: deeper than {MAX_DEPTH} folders."
    bad = [p for p in parts if not SEG_RE.match(p)]
    if bad:
        return f"{path}: file and folder names are lower case letters, digits, _ and - ({bad[0]!r})."
    if parts[0] == PACKS_DIR:
        return f"{path}: the folder packs/ is reserved for installed packs."
    if parts[0] == TEMPLATES:
        if len(parts) != 2:
            return f"{path}: templates are files directly in templates/."
        if not builder.NAME_RE.match(parts[1]):
            return f"{path}: template names are lower case letters, digits and _."
    return None


def _unsafe(name: str) -> str | None:
    if not name or "\\" in name or name.startswith("/") or ":" in name or "\x00" in name:
        return "absolute or Windows path"
    parts = name.rstrip("/").split("/")
    if any(p in ("", ".", "..") for p in parts):
        return "path leaves the pack folder"
    return None


# ------------------------------------------------------------------------------------------------ reading


def read_zip(data: bytes) -> tuple[str, dict[str, str]]:
    """Untrusted zip bytes -> ``(pack.json text, {path: text})``. Raises PackError on anything unsafe: a file
    that is not .txt / pack.json, a path out of the zip root, a symlink, encryption, too many or too big files,
    text that is not UTF-8. A zip whose files all sit in one top folder (``mypack/pack.json``) is accepted."""
    if not isinstance(data, (bytes, bytearray)) or not data:
        raise PackError("KDX Packs: no file received.")
    if len(data) > MAX_ZIP_BYTES:
        raise PackError(f"KDX Packs: the zip is larger than {MAX_ZIP_BYTES // (1024 * 1024)} MB.")
    try:
        zf = zipfile.ZipFile(io.BytesIO(bytes(data)))
    except (zipfile.BadZipFile, ValueError) as e:
        raise PackError(f"KDX Packs: not a zip file ({e}).") from e
    problems: list[str] = []
    infos = zf.infolist()
    if len(infos) > MAX_FILES + 1:
        raise PackError(f"KDX Packs: more than {MAX_FILES} files in the zip.")
    files: list[zipfile.ZipInfo] = []
    seen: set[str] = set()
    total = 0
    for info in infos:
        name = info.filename
        why = _unsafe(name)
        if why:
            problems.append(f"{name!r}: {why}.")
            continue
        mode = (info.external_attr >> 16) & 0o170000
        if mode == 0o120000:
            problems.append(f"{name}: symbolic links are not allowed.")
            continue
        if info.is_dir():
            continue
        if mode not in (0, 0o100000):
            problems.append(f"{name}: not a regular file.")
            continue
        if info.flag_bits & 0x1:
            problems.append(f"{name}: encrypted files are not allowed.")
            continue
        base = name.rsplit("/", 1)[-1]
        if base != MANIFEST and not name.endswith(".txt"):
            problems.append(f"{name}: only .txt files and pack.json are allowed.")
            continue
        if name.lower() in seen:
            problems.append(f"{name}: the zip holds this file twice.")
            continue
        seen.add(name.lower())
        if info.file_size > MAX_FILE_BYTES:
            problems.append(f"{name}: larger than {MAX_FILE_BYTES // 1024} KB.")
            continue
        total += info.file_size
        files.append(info)
    if total > MAX_TOTAL_BYTES:
        problems.append(f"the files add up to more than {MAX_TOTAL_BYTES // (1024 * 1024)} MB.")
    if problems:
        raise PackError("KDX Packs: unsafe zip: " + " ".join(problems[:8])
                        + (f" (+{len(problems) - 8} more)" if len(problems) > 8 else ""))
    names = [i.filename for i in files]
    prefix = ""
    if MANIFEST not in names:
        tops = {n.split("/", 1)[0] for n in names}
        if len(tops) == 1 and all("/" in n for n in names) and f"{next(iter(tops))}/{MANIFEST}" in names:
            prefix = next(iter(tops)) + "/"
        else:
            raise PackError("KDX Packs: pack.json is missing at the top of the zip.")
    out: dict[str, str] = {}
    manifest = ""
    read_total = 0
    for info in files:
        with zf.open(info) as f:
            raw = f.read(MAX_FILE_BYTES + 1)  # the header may lie about the size: never read more
        read_total += len(raw)
        if len(raw) > MAX_FILE_BYTES or read_total > MAX_TOTAL_BYTES:
            raise PackError(f"KDX Packs: unsafe zip: {info.filename} is larger than its header says.")
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as e:
            raise PackError(f"KDX Packs: {info.filename} is not UTF-8 text ({e.reason}).") from e
        rel = info.filename[len(prefix):]
        if rel == MANIFEST:
            manifest = text
        elif not info.filename.startswith(prefix) or rel.rsplit("/", 1)[-1] == MANIFEST:
            raise PackError(f"KDX Packs: {info.filename} is outside the pack folder.")
        else:
            out[rel] = text
    return manifest, out


def parse_meta(text: str, files: dict[str, str] | None = None) -> tuple[dict, list[dict]]:
    """pack.json text -> (normalized meta, problems). With ``files``, the file list and md5 are checked too."""
    errs: list[dict] = []
    try:
        raw = json.loads(text or "")
    except ValueError as e:
        return {}, [_msg("error", "manifest", f"pack.json is not valid JSON ({e}).", MANIFEST)]
    if not isinstance(raw, dict):
        return {}, [_msg("error", "manifest", "pack.json must be a JSON object.", MANIFEST)]

    def s(key: str, limit: int, required: bool = False, default: str = "") -> str:
        v = raw.get(key, default)
        if not isinstance(v, str) or CONTROL_RE.search(v.replace("\n", " ")) or len(v) > limit:
            errs.append(_msg("error", "manifest", f"pack.json: {key} must be text of at most {limit} characters.",
                             MANIFEST))
            return default
        v = v.strip()
        if required and not v:
            errs.append(_msg("error", "manifest", f"pack.json: {key} is required.", MANIFEST))
        return v

    if raw.get("format") != FORMAT:
        errs.append(_msg("error", "format", f"pack.json: format must be {FORMAT} (this Studio reads format {FORMAT}).",
                         MANIFEST))
    meta = {
        "format": FORMAT,
        "name": s("name", 32, True),
        "title": s("title", 80),
        "version": s("version", 16, True),
        "author": s("author", 64, True),
        "description": s("description", 2000),
        "license": s("license", 40, True),
        "nsfw": raw.get("nsfw"),
        "created": s("created", 32),
    }
    if meta["name"] and not PACK_NAME_RE.match(meta["name"]):
        errs.append(_msg("error", "name", "pack.json: name is 2-32 lower case letters, digits and _, starting with a "
                         "letter.", MANIFEST))
    if meta["version"] and not VERSION_RE.match(meta["version"]):
        errs.append(_msg("error", "version", "pack.json: version is three numbers, e.g. 1.0.0.", MANIFEST))
    if not isinstance(meta["nsfw"], bool):
        errs.append(_msg("error", "nsfw", "pack.json: nsfw must be true or false.", MANIFEST))
        meta["nsfw"] = True  # unknown = treat as NSFW
    if meta["license"] and meta["license"] not in LICENSES:
        errs.append(_msg("warn", "license", f"License {meta['license']!r} is not one of {', '.join(LICENSES)}: "
                         "read it before you share or change the pack.", MANIFEST))
    meta["title"] = meta["title"] or meta["name"]
    tpls = raw.get("templates")
    if not isinstance(tpls, list) or not all(isinstance(t, str) for t in tpls):
        errs.append(_msg("error", "manifest", "pack.json: templates must be a list of names.", MANIFEST))
        tpls = []
    meta["templates"] = list(dict.fromkeys(tpls))
    listed = raw.get("files")
    if not isinstance(listed, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in listed.items()):
        errs.append(_msg("error", "manifest", "pack.json: files must map each path to its md5.", MANIFEST))
        listed = {}
    meta["files"] = dict(sorted(listed.items()))
    if files is not None:
        have = set(files)
        for p in sorted(have - set(listed)):
            errs.append(_msg("error", "unlisted", f"{p} is in the zip but not in pack.json files.", p))
        for p in sorted(set(listed) - have):
            errs.append(_msg("error", "missing_file", f"{p} is listed in pack.json but not in the zip.", p))
        for p in sorted(have & set(listed)):
            if not MD5_RE.match(listed[p].lower()) or listed[p].lower() != md5(_text(files[p])):
                errs.append(_msg("error", "md5", f"{p}: md5 does not match pack.json (changed after export?).", p))
        real = sorted(t for t in (template_of(key_of(p)) for p in have) if t)
        if sorted(meta["templates"]) != real:
            errs.append(_msg("error", "templates", "pack.json templates must list exactly the files in templates/ ("
                             + ", ".join(real) + ").", MANIFEST))
    return meta, errs


# ------------------------------------------------------------------------------------------------ checks


def pack_library(files: dict[str, str]) -> Library:
    return Library({normalize_key(key_of(p)): parse_lines(_text(t).split("\n")) for p, t in files.items()})


def _value_lines(text: str) -> list[str]:
    return [ln.strip() for ln in _text(text).split("\n") if ln.strip() and not ln.strip().startswith("#")]


def _braces_ok(line: str) -> bool:
    depth = 0
    s = line.replace("\\{", "").replace("\\}", "")
    for c in s:
        depth += (c == "{") - (c == "}")
        if depth < 0:
            return False
    return depth == 0


def _minor(text: str) -> str | None:
    m = MINOR_RE.search(text) or AGE_RE.search(text)
    return m.group(0) if m else None


def lint(files: dict[str, str], lib: Library, nsfw: bool) -> list[dict]:
    """Per-file text rules (the library lint): one value per line, one weight, balanced braces, no control
    characters, full tokens that the pack itself holds, no minors, no NSFW template in an SFW pack."""
    out: list[dict] = []
    for path in sorted(files):
        key = key_of(path)
        why = check_path(path)
        if why:
            out.append(_msg("error", "path", why, path))
            continue
        text = files[path]
        lines = _value_lines(text)
        tpl = template_of(key)
        if CONTROL_RE.search(text):
            out.append(_msg("error", "control", "control characters in the text.", path))
        if not lines:
            out.append(_msg("error", "empty", "no values (an empty pool picks nothing).", path))
        if tpl is not None:
            if len(lines) > 1:
                out.append(_msg("warn", "one_line", f"{len(lines)} lines: a template is one line; each further line "
                                "is a random alternative.", path))
            if is_excluded(tpl) and not nsfw:
                out.append(_msg("error", "nsfw", f"template {tpl} has an NSFW name (nsfw, akt, sheer) but pack.json "
                                "says nsfw: false.", path))
        seen: set[str] = set()
        warned: set[str] = set()
        for ln in lines:
            if len(ln) > MAX_LINE:
                out.append(_msg("error", "long", f"a line longer than {MAX_LINE} characters.", path))
            if DOUBLE_WEIGHT_RE.match(ln):
                out.append(_msg("error", "weight", f"two weights on one line: {ln[:60]!r}.", path))
            if not _braces_ok(ln):
                out.append(_msg("error", "braces", f"unbalanced {{ }} in {ln[:60]!r}.", path))
            word = _minor(ln)
            if word:
                out.append(_msg("error", "minor", f"{word!r}: packs describe adults only (from the early twenties), "
                                "never a minor.", path))
            v = parse_lines([ln])[0].value.lower()
            if v in seen and "dup" not in warned:
                out.append(_msg("warn", "duplicate", f"the value {v[:60]!r} is there twice.", path))
                warned.add("dup")
            seen.add(v)
            for tok in TOKEN_RE.findall(ln):
                k = normalize_key(tok)
                if k in warned:
                    continue
                warned.add(k)
                if k.split("/", 1)[0] == PACKS_DIR:
                    out.append(_msg("error", "outside", f"__{tok}__ points into another installed pack; a pack carries "
                                    "every pool it uses.", path))
                    continue
                keys = lib.match_keys(k)
                if not keys:
                    out.append(_msg("error", "missing", f"__{tok}__: the pack has no such pool.", path))
                    continue
                if any(template_of(x) is not None for x in keys) and not (len(keys) == 1 and keys[0] == k):
                    out.append(_msg("error", "template_token", f"__{tok}__ reaches templates: write the full "
                                    "__templates/<name>__.", path))
                elif "/" not in k or "*" in k:
                    out.append(_msg("warn", "full_token", f"__{tok}__ is not a full __folder/file__ token; it pools "
                                    f"{len(keys)} file(s) of the pack.", path))
    return out


def struct(lib: Library, names: list[str], samples: int = SAMPLES, seed: int = 0) -> list[dict]:
    """Expansions per template (the library's struct check): no unknown or unresolved token, no weight leak,
    no minor; warnings for the ratio (exactly one N:N), double spaces, punctuation and a lower-case start."""
    out: list[dict] = []
    rng = random.Random(seed)
    for name in names:
        path = f"{TEMPLATES}/{name}.txt"
        key = f"{TEMPLATES}/{name}"
        if key not in lib.data:
            continue
        for w in builder.check("\n".join(e.value for e in lib.data[key]), lib, name, samples=0):
            if w["code"] in ("mood", "soft", "sky", "sex_name", "clothing"):
                out.append(_msg("warn", w["code"], w["msg"], path))
        bad: dict[str, int] = {}
        missing: set[str] = set()
        minor = ""
        for _ in range(samples):
            res = lib.expand(f"__{key}__", rng.randrange(2**31))
            x = res.text
            missing.update(res.missing)
            checks = {"unresolved": "__" in x, "leak": bool(WEIGHT_LEAK_RE.search(x)),
                      "ratio": len(RATIO_RE.findall(x)) != 1, "spaces": "  " in x,
                      "punctuation": bool(PUNCT_RE.search(x)), "lowercase": bool(x) and not x[0].isupper()}
            for c, hit in checks.items():
                if hit:
                    bad[c] = bad.get(c, 0) + 1
            minor = minor or (_minor(x) or "")

        def pct(c: str, bad: dict = bad) -> str:
            return f"{bad[c] * 100 // samples or 1} % of {samples} expansions"

        if missing:
            out.append(_msg("error", "missing", "unknown wildcards after expanding: " + ", ".join(sorted(missing)),
                            path))
        if bad.get("unresolved"):
            out.append(_msg("error", "unresolved", f"a __token__ is left in {pct('unresolved')}.", path))
        if bad.get("leak"):
            out.append(_msg("error", "weight_leak", f"a weight N:: shows in the text in {pct('leak')}.", path))
        if minor:
            out.append(_msg("error", "minor", f"an expansion contains {minor!r}: adults only, never a minor.", path))
        for code, what in (("ratio", "do not contain exactly one aspect ratio N:N"), ("spaces", "have a double space"),
                           ("punctuation", "have broken punctuation"), ("lowercase", "start in lower case")):
            if bad.get(code):
                out.append(_msg("warn", code, f"{pct(code)} {what}.", path))
    return out


def validate(meta: dict, files: dict[str, str], *, samples: int = SAMPLES) -> list[dict]:
    """Every rule a pack must pass (pack.json problems not included): lint + struct."""
    lib = pack_library(files)
    msgs = lint(files, lib, bool(meta.get("nsfw")))
    tpls = sorted(t for t in (template_of(key_of(p)) for p in files) if t)
    if not tpls:
        msgs.append(_msg("error", "no_templates", "the pack has no template (templates/<name>.txt)."))
    if len(tpls) > MAX_TEMPLATES:
        msgs.append(_msg("error", "too_many", f"more than {MAX_TEMPLATES} templates."))
    if not any(m["level"] == "error" and m["code"] in ("path", "braces", "outside") for m in msgs):
        msgs += struct(lib, tpls, samples)
    return msgs


def split(msgs: list[dict]) -> tuple[list[dict], list[dict]]:
    return [m for m in msgs if m["level"] == "error"], [m for m in msgs if m["level"] != "error"]


def samples(files: dict[str, str], count: int = 3, seed: int = 1) -> list[dict]:
    """``count`` example prompts, taking the templates in turn (what the pack gives after install)."""
    lib = pack_library(files)
    tpls = sorted(t for t in (template_of(key_of(p)) for p in files) if t)
    out = []
    for i in range(count if tpls else 0):
        t = tpls[i % len(tpls)]
        out.append({"template": t, "seed": seed + i, "text": lib.expand(f"__{TEMPLATES}/{t}__", seed + i).text})
    return out


# ------------------------------------------------------------------------------------------------ export


def collect(lib: Library, names: list[str]) -> dict[str, str]:
    """The templates and every pool they reach (recursively, glob and short names included) -> {path: text}.
    Files are copied as they are (comments and weights kept)."""
    if not names:
        raise PackError("KDX Packs: pick at least one template.")
    todo = [f"{TEMPLATES}/{n}" for n in names]
    for k in todo:
        if k not in lib.data:
            raise PackError(f"KDX Packs: no template {template_of(k)!r} in the library.")
    seen: set[str] = set()
    out: dict[str, str] = {}
    while todo:
        k = todo.pop()
        if k in seen:
            continue
        seen.add(k)
        if k.split("/", 1)[0] == PACKS_DIR:
            raise PackError(f"KDX Packs: {k} belongs to an installed pack. Share that pack's own zip instead, or "
                            "pick templates of your own library.")
        src = lib.sources.get(k)
        if src:
            with open(src, encoding="utf-8-sig", errors="replace") as f:
                text = _text(f.read())
        else:  # in-memory library (tests)
            text = _text("\n".join(f"{e.weight:g}::{e.value}" if e.weight != 1 else e.value for e in lib.data[k]))
        out[k] = text
        for ln in _value_lines(text):
            for tok in TOKEN_RE.findall(ln):
                todo.extend(x for x in lib.match_keys(tok) if x not in seen)
    # templates in sub-folders (templates/people/portrait) become flat names (people_portrait) in a pack
    flat = {k: f"{TEMPLATES}/{t.replace('/', '_')}" for k in out if (t := template_of(k)) and "/" in t}
    if flat:
        def tok(m: re.Match) -> str:
            k = normalize_key(m.group(1))
            return f"__{flat[k]}__" if k in flat else m.group(0)

        out = {flat.get(k, k): "\n".join(ln if ln.lstrip().startswith("#") else TOKEN_RE.sub(tok, ln)
                                         for ln in t.split("\n")) for k, t in out.items()}
    return dict(sorted((f"{k}.txt", t) for k, t in out.items()))


def make_meta(raw: dict, files: dict[str, str]) -> dict:
    """pack.json for an export: the user's fields + templates, files and md5. nsfw is true when asked for or
    when a template has an NSFW name."""
    tpls = sorted(t for t in (template_of(key_of(p)) for p in files) if t)
    name = str(raw.get("name") or "").strip().lower()
    return {
        "format": FORMAT,
        "name": name,
        "title": str(raw.get("title") or name).strip()[:80],
        "version": str(raw.get("version") or "1.0.0").strip(),
        "author": str(raw.get("author") or "").strip()[:64],
        "description": str(raw.get("description") or "").strip()[:2000],
        "license": str(raw.get("license") or DEFAULT_LICENSE).strip()[:40],
        "nsfw": bool(raw.get("nsfw")) or any(is_excluded(t) for t in tpls),
        "created": _dt.date.today().isoformat(),
        "templates": tpls,
        "files": {p: md5(t) for p, t in sorted(files.items())},
    }


def build_zip(meta: dict, files: dict[str, str]) -> bytes:
    """Deterministic zip: pack.json first, then the files sorted, fixed timestamps."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        def put(path: str, text: str) -> None:
            info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            zf.writestr(info, text.encode("utf-8"))

        put(MANIFEST, json.dumps(meta, indent=2, ensure_ascii=False) + "\n")
        for p, t in sorted(files.items()):
            put(p, t)
    return buf.getvalue()


def export(lib: Library, names: list[str], raw_meta: dict, *, samples_n: int = SAMPLES) -> dict:
    """``{meta, files, errors, warnings, zip}``; ``zip`` is None while there are errors."""
    files = collect(lib, names)
    meta = make_meta(raw_meta, files)
    _m, merr = parse_meta(json.dumps(meta), files)
    errors, warnings = split(merr + validate(meta, files, samples=samples_n))
    size = sum(len(t.encode("utf-8")) for t in files.values())
    return {"meta": meta, "files": sorted(files), "size": size, "errors": errors, "warnings": warnings,
            "zip": None if errors else build_zip(meta, files)}


# ------------------------------------------------------------------------------------------------ install


def installed_name(pack: str, name: str, nsfw: bool, taken: set[str]) -> str:
    base = name if name.startswith(pack + "_") else f"{pack}_{name}"
    if nsfw and not is_excluded(base):
        base = "nsfw_" + base
    cand, i = base, 2
    while cand in taken:
        cand, i = f"{base}_{i}", i + 1
    if not builder.NAME_RE.match(cand):
        raise PackError(f"KDX Packs: the template name {cand!r} is too long; use a shorter pack or template name.")
    return cand


def rewrite(text: str, pack: str, tmap: dict[str, str]) -> str:
    """Point every token at the pack's own namespace (comment lines stay as written)."""

    def tok(m: re.Match) -> str:
        k = normalize_key(m.group(1))
        t = template_of(k)
        if t is not None and t in tmap:
            return f"__{TEMPLATES}/{tmap[t]}__"
        return f"__{PACKS_DIR}/{pack}/{k}__"

    lines = _text(text).split("\n")
    return "\n".join(ln if ln.lstrip().startswith("#") else TOKEN_RE.sub(tok, ln) for ln in lines)


def _entries_equal(a, b) -> bool:
    return [(e.value, e.weight) for e in a] == [(e.value, e.weight) for e in b]


def plan(meta: dict, files: dict[str, str], lib: Library, installed: dict | None = None) -> dict:
    """What an install would do: template names (``installed_as``), pools and how they compare with the user's
    library (``new`` / ``same`` / ``differs``: the user's own pool stays either way)."""
    pack = meta["name"]
    own = set((installed or {}).get("installed", {}).get("templates", {}).values())
    taken = {t for k in lib.data if (t := template_of(k))} - own
    plib = pack_library(files)
    tmap: dict[str, str] = {}
    tpls, pools = [], []
    for p in sorted(files):
        key = key_of(p)
        t = template_of(key)
        if t is not None:
            inst = installed_name(pack, t, bool(meta.get("nsfw")), taken | set(tmap.values()))
            tmap[t] = inst
            tpls.append({"name": t, "installed_as": inst, "exists": f"{TEMPLATES}/{t}" in lib.data})
        else:
            status = "new"
            if key in lib.data:
                status = "same" if _entries_equal(lib.data[key], plib.data.get(key, [])) else "differs"
            pools.append({"key": key, "installed_as": f"{PACKS_DIR}/{pack}/{key}", "status": status,
                          "values": len(plib.data.get(key, []))})
    return {"templates": tpls, "pools": pools, "tmap": tmap}


def _inside(root: str, path: str) -> str:
    real_root, real = os.path.realpath(root), os.path.realpath(path)
    if os.path.commonpath([real_root, real]) != real_root:
        raise PackError(f"KDX Packs: refusing to write outside the wildcard folder ({path}).")
    return path


def _write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    builder._atomic_write(path, text.encode("utf-8"))


def read_installed(root: str, name: str) -> dict | None:
    path = os.path.join(root, PACKS_DIR, name, MANIFEST)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def list_installed(roots: list[str]) -> list[dict]:
    """Installed packs in the wildcard folders: their pack.json (+ ``root``), sorted by name."""
    out, seen = [], set()
    for root in roots:
        base = os.path.join(root, PACKS_DIR)
        if not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base)):
            if name in seen or not PACK_NAME_RE.match(name) or os.path.islink(os.path.join(base, name)):
                continue
            meta = read_installed(root, name)
            if meta is None:
                continue
            seen.add(name)
            inst = meta.get("installed") or {}
            out.append({k: meta.get(k) for k in ("name", "title", "version", "author", "description", "license",
                                                  "nsfw", "created")}
                       | {"name": name, "nsfw": meta.get("nsfw") is not False,
                          "templates": sorted((inst.get("templates") or {}).values()),
                          "installed_at": inst.get("at", ""), "pools": inst.get("pools", 0), "root": root})
    return out


def install(root: str, meta: dict, files: dict[str, str], lib: Library, *, replace: bool = False) -> dict:
    """Write a checked pack into ``root`` (see the module doc). Raises PackExists when the pack is installed and
    not ``replace``. On replace, the old pack's templates that the new version no longer has are removed."""
    pack = meta["name"]
    if not PACK_NAME_RE.match(pack or ""):
        raise PackError("KDX Packs: invalid pack name.")
    root = os.path.abspath(root)
    base = _inside(root, os.path.join(root, PACKS_DIR))
    target = _inside(root, os.path.join(base, pack))
    old = read_installed(root, pack) if os.path.isdir(target) else None
    if os.path.lexists(target):
        if os.path.islink(target):
            raise PackError(f"KDX Packs: {target} is a link; remove it by hand.")
        if not replace:
            raise PackExists(f"KDX Packs: the pack {pack} is installed already"
                             + (f" (version {old.get('version')})." if old else "."))
    pl = plan(meta, files, lib, old)
    tmap = pl["tmap"]
    os.makedirs(base, exist_ok=True)
    stage = tempfile.mkdtemp(prefix=f".{pack}.staging-", dir=base)
    written: list[str] = []
    try:
        tmd5 = {}
        for p in sorted(files):
            text = rewrite(files[p], pack, tmap)
            t = template_of(key_of(p))
            if t is None:
                _write(_inside(root, os.path.join(stage, *p.split("/"))), text)
            else:
                dest = _inside(root, os.path.join(root, TEMPLATES, tmap[t] + ".txt"))
                if os.path.isfile(dest) and _edited(dest, old, tmap[t]):  # the user changed it: keep a copy
                    shutil.copy2(dest, dest + ".bak")
                _write(dest, text)
                written.append(dest)
                tmd5[tmap[t]] = md5(_text(text))
        record = {k: meta.get(k) for k in ("format", "name", "title", "version", "author", "description", "license",
                                            "nsfw", "created", "templates", "files")}
        record["installed"] = {"at": _dt.datetime.now().isoformat(timespec="seconds"), "templates": tmap,
                               "md5": tmd5, "pools": len(pl["pools"])}
        _write(os.path.join(stage, MANIFEST), json.dumps(record, indent=2, ensure_ascii=False) + "\n")
        removed: list[str] = []
        if os.path.isdir(target):
            old_names = set(((old or {}).get("installed") or {}).get("templates", {}).values())
            for t in sorted(old_names - set(tmap.values())):
                f = os.path.join(root, TEMPLATES, t + ".txt")
                if builder.NAME_RE.match(t) and os.path.isfile(f) and not _edited(f, old, t):
                    os.remove(f)
                    removed.append(t)
            shutil.rmtree(target)
        os.replace(stage, target)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        if not old:
            for f in written:
                try:
                    os.remove(f)
                except OSError:
                    pass
        raise
    return {"name": pack, "version": meta.get("version"), "templates": tmap, "pools": len(pl["pools"]),
            "removed": removed, "replaced": old is not None, "path": target}


def _edited(path: str, record: dict | None, name: str) -> bool:
    """True when the installed template file was changed after the install (or has no record)."""
    sums = ((record or {}).get("installed") or {}).get("md5") or {}
    try:
        with open(path, encoding="utf-8-sig", errors="replace") as fh:
            return md5(_text(fh.read())) != sums.get(name)
    except OSError:
        return False


def uninstall(root: str, name: str) -> dict:
    """Remove ``packs/<name>/`` and the pack's template files. A template file changed since the install
    (md5 differs) is kept and listed in ``kept``."""
    if not PACK_NAME_RE.match(str(name or "")):
        raise PackError("KDX Packs: invalid pack name.")
    root = os.path.abspath(root)
    target = _inside(root, os.path.join(root, PACKS_DIR, name))
    if os.path.islink(target):
        raise PackError(f"KDX Packs: {target} is a link; remove it by hand.")
    if not os.path.isdir(target):
        raise PackError(f"KDX Packs: the pack {name} is not installed.")
    meta = read_installed(root, name) or {}
    inst = meta.get("installed") or {}
    removed, kept = [], []
    for t in sorted(set((inst.get("templates") or {}).values())):
        if not builder.NAME_RE.match(str(t)):
            continue
        f = os.path.join(root, TEMPLATES, t + ".txt")
        if not os.path.isfile(f):
            continue
        if not _edited(f, meta, t):
            os.remove(f)
            removed.append(t)
        else:
            kept.append(t)
    shutil.rmtree(target)
    return {"name": name, "removed": removed, "kept": kept}


def inspect(data: bytes, lib: Library, lookup=None, *, samples_n: int = SAMPLES) -> dict:
    """Read and check an uploaded zip; what an install would add. ``lookup(name)`` gives the installed pack.json
    of that name (or None). Raises PackError when the zip is unsafe."""
    manifest, files = read_zip(data)
    meta, merr = parse_meta(manifest, files)
    installed = lookup(meta["name"]) if lookup and PACK_NAME_RE.match(meta.get("name") or "") else None
    msgs = merr + (validate(meta, files, samples=samples_n) if not any(m["code"] == "path" for m in merr) else [])
    errors, warnings = split(msgs)
    out = {"pack": {k: meta.get(k) for k in ("name", "title", "version", "author", "description", "license", "nsfw",
                                             "created", "templates")},
           "errors": errors, "warnings": warnings, "templates": [], "pools": [], "samples": [],
           "installed": (installed or {}).get("version") if installed else None,
           "size": sum(len(t.encode("utf-8")) for t in files.values())}
    if meta.get("name") and PACK_NAME_RE.match(meta["name"]):
        try:
            pl = plan(meta, files, lib, installed)
            out["templates"], out["pools"] = pl["templates"], pl["pools"]
        except PackError as e:
            out["errors"].append(_msg("error", "name", str(e)))
    if not any(m["code"] in ("path", "braces") for m in errors):
        out["samples"] = samples(files)
    out["can_install"] = not out["errors"]
    return {**out, "_meta": meta, "_files": files}
