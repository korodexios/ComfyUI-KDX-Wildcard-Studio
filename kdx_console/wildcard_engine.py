"""KDX wildcard engine — expands ``__key__`` and ``{a|b}`` prompts from ``.txt`` files.

Own implementation (MIT), no ComfyUI and no Impact Pack import. It reads the same kind of
wildcard library (folders of ``.txt`` files, one value per line) and understands the syntax
that library uses. The behaviour is specified in docs/07-wildcards.md; in short:

Files
    ``<root>/person/age.txt`` -> key ``person/age``. Keys are lower case, ``\\`` -> ``/``,
    spaces -> ``-``. One value per line; empty lines and lines starting with ``#`` are skipped.
    A line may start with a weight: ``3::often`` / ``0.5::rare``. Several roots may be given;
    for a key that exists in more than one root, the first root wins.

Tokens ``__key__``
    exact key -> one random line of that file (weighted). Without an exact match:
    a name with ``*`` is a glob over keys (``__person/*__``, ``__*/age__``); a name without
    ``/`` pools every file whose base name is that name or that lies in a folder of that name.
    Pools are merged with their weights. A token that matches nothing stays in the text as
    written and is reported in ``Expansion.missing``.

Options ``{a|b|c}``
    One option, weighted with ``w::`` like file lines. Innermost braces first, so
    ``{a|{b|c}}`` picks between ``a`` and the result of ``{b|c}``.
    Multi-select: ``{2$$a|b|c}`` (2 different options), ``{1-3$$...}``, ``{-3$$...}`` (1-3),
    ``{2$$ and $$a|b|c}`` (custom separator; default ``", "``). ``{2-3$$, $$__x__}`` selects
    2-3 different lines of the wildcard ``x``.

Other
    The result is expanded again until nothing changes (max ``MAX_PASSES``), so values may
    contain tokens and options. ``\\{ \\} \\|`` are literal characters. Lines of the input that
    start with ``#`` are dropped. Everything else, e.g. ``<lora:x:1>``, passes unchanged.
    The same text and seed give the same result.
"""

from __future__ import annotations

import fnmatch
import os
import random
import re
import threading
from dataclasses import dataclass, field

MAX_PASSES = 100
DEFAULT_SEPARATOR = ", "

_TOKEN_RE = re.compile(r"__([\w.\-+/*\\ ]+?)__")
_INNER_BRACE_RE = re.compile(r"\{([^{}]*)\}")  # escapes are swapped out before matching
_WEIGHT_RE = re.compile(r"^\s*(\d+(?:\.\d+)?|\.\d+)::(.*)$", re.S)
_COUNT_RE = re.compile(r"^\s*(\d*)\s*(?:-\s*(\d*))?\s*$")
#: Top folder of installed packs (see packs.py); reserved, globs and short names outside it skip it.
PACKS_DIR = "packs"
_PACK_SCOPE_RE = re.compile(r"^(packs/[^/]+/)(.+)$")

# Escaped characters are swapped for private-use code points while expanding and restored at the end.
_ESCAPES = {"\\{": "", "\\}": "", "\\|": ""}
_UNESCAPE = {v: k[1] for k, v in _ESCAPES.items()}
_UNRESOLVED = ""  # stands for "_" of a token that matched nothing, so it is not retried
_UNESCAPE[_UNRESOLVED] = "_"


def normalize_key(key: str) -> str:
    k = str(key).strip().replace("\\", "/").lower()
    k = re.sub(r"\s+", "-", k)
    return re.sub(r"/+", "/", k).strip("/")


def parse_weight(text: str) -> tuple[float, str]:
    """``"3::red"`` -> ``(3.0, "red")``; no or invalid weight -> ``(1.0, text)``."""
    m = _WEIGHT_RE.match(text)
    if not m:
        return 1.0, text
    return float(m.group(1)), m.group(2)


@dataclass
class Entry:
    value: str
    weight: float = 1.0


@dataclass
class Expansion:
    text: str
    missing: list[str] = field(default_factory=list)


class Library:
    """A loaded wildcard library: ``key -> [Entry]``."""

    def __init__(self, data: dict[str, list[Entry]] | None = None, sources: dict[str, str] | None = None):
        self.data: dict[str, list[Entry]] = dict(data or {})
        self.sources: dict[str, str] = dict(sources or {})
        self.duplicates: list[str] = []

    # ------------------------------------------------------------------ loading

    @classmethod
    def from_dirs(cls, dirs) -> Library:
        lib = cls()
        for root in dirs or []:
            root = os.path.abspath(os.path.expanduser(str(root)))
            if not os.path.isdir(root):
                continue
            for path in _walk_txt(root):
                key = normalize_key(os.path.splitext(os.path.relpath(path, root))[0])
                if key in lib.data:
                    lib.duplicates.append(f"{key}: {path} (ignored, already from {lib.sources[key]})")
                    continue
                lib.data[key] = read_entries(path)
                lib.sources[key] = path
        return lib

    @classmethod
    def from_mapping(cls, mapping: dict[str, list[str] | str]) -> Library:
        """Test helper: ``{"color": ["red", "2::blue"]}`` or ``{"color": "red\\nblue"}``."""
        data = {}
        for key, lines in mapping.items():
            if isinstance(lines, str):
                lines = lines.splitlines()
            data[normalize_key(key)] = parse_lines(lines)
        return cls(data)

    def keys(self) -> list[str]:
        return sorted(self.data)

    # ------------------------------------------------------------------ lookup

    def match_keys(self, name: str) -> list[str]:
        """The keys a token name reads (sorted; one key for an exact match, empty when nothing matches).

        Installed packs live under ``packs/<pack>/``. A glob or short name outside a pack never reaches
        into a pack, and ``packs/<pack>/<name>`` applies the same rules inside that pack only, so a pack
        behaves exactly as it did on its own and never changes what the rest of the library picks."""
        key = normalize_key(name)
        if key in self.data:
            return [key]
        m = _PACK_SCOPE_RE.match(key)
        if m:
            scope, key = m.group(1), m.group(2)
            cands = {k[len(scope):]: k for k in self.data if k.startswith(scope)}
        else:
            cands = {k: k for k in self.data if not k.startswith(PACKS_DIR + "/")}
        if "*" in key:
            pat = re.compile(fnmatch.translate(key))
            keys = [full for k, full in cands.items() if pat.match(k)]
        elif "/" not in key:
            keys = [full for k, full in cands.items()
                    if k.rsplit("/", 1)[-1] == key or k.startswith(key + "/") or f"/{key}/" in f"/{k}"]
        else:
            keys = [full for k, full in cands.items() if k.startswith(key + "/")]
        return sorted(keys)

    def pool(self, name: str) -> list[Entry] | None:
        """Entries for a token name, or ``None`` when nothing matches."""
        keys = self.match_keys(name)
        if not keys:
            return None
        if len(keys) == 1:
            return self.data[keys[0]]
        merged: list[Entry] = []
        for k in keys:
            merged.extend(self.data[k])
        return merged

    # ------------------------------------------------------------------ expansion

    def expand(self, text: str, seed: int | None = None) -> Expansion:
        rng = random.Random(seed)
        missing: list[str] = []
        s = _strip_comment_lines(str(text or ""))
        for k, v in _ESCAPES.items():
            s = s.replace(k, v)
        for _ in range(MAX_PASSES):
            new = self._pass(s, rng, missing)
            if new == s:
                break
            s = new
        for k, v in _UNESCAPE.items():
            s = s.replace(k, v)
        return Expansion(s, sorted(set(missing)))

    def _pass(self, s: str, rng: random.Random, missing: list[str]) -> str:
        # 1) innermost option groups, left to right
        s = _INNER_BRACE_RE.sub(lambda m: self._options(m.group(1), rng, missing), s)
        # 2) wildcard tokens; each occurrence is an independent pick
        return _TOKEN_RE.sub(lambda m: self._token(m, rng, missing), s)

    def _token(self, m: re.Match, rng: random.Random, missing: list[str]) -> str:
        entries = self.pool(m.group(1))
        if not entries:
            missing.append(m.group(1))
            return m.group(0).replace("_", _UNRESOLVED)  # kept as written, not retried
        return _pick(entries, rng).value

    def _options(self, body: str, rng: random.Random, missing: list[str]) -> str:
        count_part, sep, rest = None, DEFAULT_SEPARATOR, body
        if "$$" in body:
            parts = body.split("$$")
            if len(parts) >= 3 and _COUNT_RE.match(parts[0]):
                count_part, sep, rest = parts[0], parts[1], "$$".join(parts[2:])
            elif _COUNT_RE.match(parts[0]):
                count_part, rest = parts[0], "$$".join(parts[1:])
        options = []
        for opt in rest.split("|"):
            w, value = parse_weight(opt)
            options.append(Entry(value, w))
        if count_part is None:
            return _pick(options, rng).value
        # multi-select over one wildcard: choose among its lines
        if len(options) == 1:
            t = _TOKEN_RE.fullmatch(options[0].value.strip())
            if t:
                pool = self.pool(t.group(1))
                if not pool:
                    missing.append(t.group(1))
                    return options[0].value.replace("_", _UNRESOLVED)
                options = list(pool)
        lo, hi = _parse_count(count_part, len(options))
        n = rng.randint(lo, hi) if hi >= lo else 0
        return sep.join(e.value for e in _sample(options, n, rng))


# ---------------------------------------------------------------------------- helpers


def _walk_txt(root: str):
    for dirpath, dirnames, filenames in os.walk(root, followlinks=True):
        dirnames.sort()
        for f in sorted(filenames):
            if f.lower().endswith(".txt"):
                yield os.path.join(dirpath, f)


def parse_lines(lines) -> list[Entry]:
    out = []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        w, value = parse_weight(line)
        out.append(Entry(value.strip(), w))
    return out


def read_entries(path: str) -> list[Entry]:
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        return parse_lines(f)


def _strip_comment_lines(s: str) -> str:
    if "#" not in s:
        return s
    return "\n".join(line for line in s.split("\n") if not line.lstrip().startswith("#"))


def _pick(entries: list[Entry], rng: random.Random) -> Entry:
    total = sum(max(e.weight, 0.0) for e in entries)
    if total <= 0:
        return entries[rng.randrange(len(entries))]
    r = rng.random() * total
    acc = 0.0
    for e in entries:
        acc += max(e.weight, 0.0)
        if r < acc:
            return e
    return entries[-1]


def _sample(entries: list[Entry], n: int, rng: random.Random) -> list[Entry]:
    """``n`` different entries (weighted, without replacement), in pick order."""
    pool = list(entries)
    out = []
    for _ in range(min(n, len(pool))):
        e = _pick(pool, rng)
        out.append(e)
        pool.remove(e)
    return out


def _parse_count(part: str, available: int) -> tuple[int, int]:
    m = _COUNT_RE.match(part or "")
    a, b = (m.group(1), m.group(2)) if m else ("", None)
    if b is None:  # "n"
        lo = hi = int(a) if a else 1
    else:  # "n-m", "-m", "n-"
        lo = int(a) if a else 1
        hi = int(b) if b else available
    lo, hi = max(0, lo), max(0, hi)
    if lo > hi:
        lo, hi = hi, lo
    return min(lo, available), min(hi, available)


# ---------------------------------------------------------------------------- cached library


class CachedLibrary:
    """Reloads the library when a file under the roots is added, removed or changed."""

    def __init__(self):
        self._lock = threading.Lock()
        self._sig = None
        self._lib = Library()

    def get(self, dirs) -> Library:
        dirs = [os.path.abspath(os.path.expanduser(str(d))) for d in dirs or []]
        sig = (tuple(dirs), _signature(dirs))
        with self._lock:
            if sig != self._sig:
                self._lib = Library.from_dirs(dirs)
                self._sig = sig
            return self._lib


def _signature(dirs) -> tuple:
    items = []
    for root in dirs:
        if not os.path.isdir(root):
            items.append((root, None))
            continue
        for path in _walk_txt(root):
            try:
                st = os.stat(path)
            except OSError:
                continue
            items.append((path, st.st_mtime_ns, st.st_size))
    return tuple(items)
