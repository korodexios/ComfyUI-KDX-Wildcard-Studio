"""Keep parts: take a prompt apart into the picks that made it, keep some of them, let the rest vary.

Pure logic, no ComfyUI imports. The input is what made an image: the text that was expanded (a template token
such as ``__templates/portrait_woman__``, a builder line or the user's own text) and the seed. The expansion is
repeated with a trace (:meth:`Library.expand` with ``trace=True``: the same picks in the same order), so every
part of the prompt is known by the pick that produced it.

Keeping a part (``locks``: node ids) builds a new template line:

* a kept pick becomes its text, written literally (``{ } |`` escaped);
* a pick with a kept part inside keeps its choice: the option / line it took, with its other parts as they
  were written (so keeping the expression of ``{her expression is __a__. The mood is __b__|…}`` keeps that
  option, and the mood stays a wildcard unless it is kept too);
* everything else is written back as the wildcard syntax it came from.

Two self checks make sure the record is right before anything is offered: the record written back without
locks expands with the same seed to the same prompt, and the record with every leaf kept expands to that
prompt without any randomness left.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from .wildcard_engine import _ESCAPES, _UNESCAPE, _UNRESOLVED, Library, Trace

_TO_SRC = {v: k for k, v in _ESCAPES.items()}
_TO_SRC[_UNRESOLVED] = "_"
_LITERAL = {"{": "\\{", "}": "\\}", "|": "\\|"}
_SOLO_SPLIT = re.compile(r"\||\$\$")


MAX_SWAP = 2000  # characters of one replacement or of the added text


class KeepError(ValueError):
    """A request the keep tool cannot answer (readable message for the user)."""


def _src(s: str) -> str:
    """Internal characters -> wildcard syntax as written."""
    return "".join(_TO_SRC.get(c, c) for c in s)


def _lit(s: str) -> str:
    """Internal characters -> text that expands to exactly itself."""
    return "".join(_TO_SRC.get(c) or _LITERAL.get(c, c) for c in s)


def _show(s: str) -> str:
    """Internal characters -> the text as the prompt shows it."""
    return "".join(_UNESCAPE.get(c, c) for c in s)


# ---------------------------------------------------------------------------------------------------- groups

#: Quick choices. Every token is in at most one group (first rule that matches its name wins); "person" is
#: the face group and the body group together. Order matters: "pose/city_scene" is a pose, not a place.
GROUPS: list[tuple[str, str, str]] = [
    ("clothing", "Clothing", r"cloth|outfit|wear|dress|accessor|shoe|jewel"),
    ("company", "Other people", r"(^|/)(company|two|group)/|companion|couple|crowd"),
    ("pose", "Pose & action", r"(^|/)(pose|activity)/|motion|situation|action|pose|(^|[/_])act($|_)|touch"),
    ("camera", "Camera", r"camera|shot|lens|composition|gear|angle|distance|capture|optic|framing|focal|focus"),
    ("face", "Face & hair", r"express|gaze|(^|[/_])eye|(^|[/_])face|facial|lips|nose|makeup|hair|skin|smile"
                            r"|imperfection"),
    ("body", "Body & age", r"(^|/)(person|man|woman|men|women)/|(^|[/_])age|ethnic|(^|[/_])build($|_)|body|figure"),
    ("scene", "Environment & light", r"place|location|scene|setting|background|room|weather|light|sky|landscape"
                                     r"|surface|interior|exterior|season|(^|[/_])time"),
    ("style", "Style & mood", r"medium|realism|palette|mood|style|(^|[/_])art|film|colou?r|grade|(^|[/_])tone"
                              r"|detail|look"),
    ("subject", "Subject", r"subject|object|dish|animal|creature|vehicle|building|architecture|food|still"),
]
_GROUP_RES = [(gid, label, re.compile(rx)) for gid, label, rx in GROUPS]
COMBINED = {"person": ("Whole person", ("face", "body"))}


def group_of(name: str) -> str | None:
    """Group id of a token name (``person/hair`` -> ``face``), or None."""
    key = str(name or "").strip().lower().replace("\\", "/")
    if key.startswith("templates/"):  # a whole template is not a part of a picture
        return None
    for gid, _label, rx in _GROUP_RES:
        if rx.search(key):
            return gid
    return None


# ----------------------------------------------------------------------------------------------- the record


@dataclass
class Part:
    id: int
    kind: str  # root | token | options
    name: str
    source: str  # internal characters
    parent: int
    missing: bool
    segs: list  # str (internal characters) | Part


class Decomposition:
    """A traced expansion as a tree of :class:`Part`; ``prompt`` is the expanded text."""

    def __init__(self, text: str, seed: int, prompt: str, missing: list[str], trace: Trace):
        self.text = text
        self.seed = seed
        self.prompt = prompt
        self.missing = missing
        self.fragile = trace.fragile
        self.parts: dict[int, Part] = {}
        self.root = self._build(trace)

    # tree -----------------------------------------------------------------------------------------------
    def _build(self, tr: Trace) -> Part:
        def part(n: int) -> Part:
            if n not in self.parts:
                node = tr.nodes[n]
                self.parts[n] = Part(n, node.kind, node.name, node.source, node.parent, node.missing, [])
            return self.parts[n]

        root = part(0)
        stack: list[int] = [0]
        closed: set[int] = set()
        for owner, ch in tr.cells:
            chain = []
            n = owner
            while n >= 0:
                chain.append(n)
                n = tr.nodes[n].parent
            chain.reverse()
            k = 0
            while k < len(stack) and k < len(chain) and stack[k] == chain[k]:
                k += 1
            for gone in stack[k:]:
                closed.add(gone)
            stack = stack[:k]
            for n in chain[k:]:
                if n in closed:  # a pick that shows up in two places: its record was cut apart
                    self.fragile = True
                p = part(n)
                part(stack[-1]).segs.append(p)
                stack.append(n)
            if ch:
                segs = part(stack[-1]).segs
                if segs and isinstance(segs[-1], str):
                    segs[-1] += ch
                else:
                    segs.append(ch)
        return root

    def text_of(self, p: Part) -> str:
        return "".join(s if isinstance(s, str) else self.text_of(s) for s in p.segs)

    def children(self, p: Part) -> list[Part]:
        return [s for s in p.segs if isinstance(s, Part)]

    def walk(self, p: Part | None = None):
        p = p or self.root
        yield p
        for c in self.children(p):
            yield from self.walk(c)

    def ancestors(self, pid: int) -> list[int]:
        out = []
        n = self.parts[pid].parent
        while n >= 0:
            out.append(n)
            n = self.parts[n].parent
        return out

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(f"{self.text}\0{self.seed}\0{self.prompt}".encode()).hexdigest()[:16]

    # render ---------------------------------------------------------------------------------------------
    def clean_locks(self, locks) -> set[int]:
        """Known, lockable ids; a lock inside a kept part is redundant and dropped."""
        ids = set()
        for x in locks or []:
            try:
                i = int(x)
            except (TypeError, ValueError):
                continue
            if i in self.parts and i != 0:
                ids.add(i)
        return {i for i in ids if not any(a in ids for a in self.ancestors(i))}

    def clean_swaps(self, swaps, locks) -> dict:
        """Replacements: part id -> text, or ``"<part>.<seg>.<piece>"`` -> text for a piece of literal text (see
        :func:`pieces`). One line each, wildcards allowed, empty = drop it. A replacement inside a kept or another
        replaced part is dropped."""
        locked = self.clean_locks(locks)
        part_sw: dict[int, str] = {}
        text_sw: dict[str, str] = {}
        for k, val in (swaps or {}).items() if isinstance(swaps, dict) else []:
            if not isinstance(val, str):
                continue
            text = " ".join(val.split())[:MAX_SWAP]
            key = str(k)
            if "." in key:
                if self._piece(key) is not None:
                    text_sw[key] = text
                continue
            try:
                i = int(key)
            except ValueError:
                continue
            if i in self.parts and i != 0:
                part_sw[i] = text
        part_sw = {i: t for i, t in part_sw.items()
                   if i not in locked and not any(a in locked for a in self.ancestors(i))}
        part_sw = {i: t for i, t in part_sw.items() if not any(a in part_sw for a in self.ancestors(i))}
        out: dict = dict(part_sw)
        for key, t in text_sw.items():
            pid = int(key.split(".")[0])
            if pid not in part_sw and not any(a in part_sw for a in self.ancestors(pid)):
                out[key] = t
        return out

    def _piece(self, key: str) -> tuple[int, int, int] | None:
        """``"<part>.<seg>.<piece>"`` -> numbers, when that piece exists and has words."""
        try:
            pid, si, k = (int(x) for x in key.split("."))
        except ValueError:
            return None
        part = self.parts.get(pid)
        if part is None or not (0 <= si < len(part.segs)) or not isinstance(part.segs[si], str):
            return None
        ps = pieces(part.segs[si])
        return (pid, si, k) if 0 <= k < len(ps) and ps[k][1] else None

    def top_plain(self) -> set[int]:
        """Parts whose own text is plain text outside any pick: the prompt, the chosen template line and ``{x}``
        wrappers, when everything around them is plain as well."""
        out = set()
        for p in self.walk():
            if is_plain(p) and all(is_plain(self.parts[a]) for a in self.ancestors(p.id)):
                out.add(p.id)
        return out

    def render(self, locks, swaps=None, append: str = "", marks=None, drop_text: bool = False) -> str:
        """The template line with ``locks`` kept and ``swaps`` put in place of parts or pieces of text; the choices
        around a kept or replaced part (or text) are kept. ``marks`` are pieces of plain text you keep; with
        ``drop_text`` every other piece of plain text (outside the picks) is left out, so only the wildcards, the
        kept parts and the marked text stay. ``append`` goes at the end (see the module docstring)."""
        swapped = self.clean_swaps(swaps, locks)
        part_sw = {k: v for k, v in swapped.items() if isinstance(k, int)}
        text_sw = {k: v for k, v in swapped.items() if isinstance(k, str)}

        def free_of_swaps(pid: int) -> bool:
            return pid not in part_sw and not any(a in part_sw for a in self.ancestors(pid))

        marked = {k for k in (str(x) for x in marks or [])
                  if self._piece(k) is not None and k not in text_sw and free_of_swaps(int(k.split(".")[0]))}
        dropping = {p for p in self.top_plain() if free_of_swaps(p)} if drop_text else set()
        text_parts = {int(k.split(".")[0]) for k in [*text_sw, *marked]} | dropping
        holds_text = set(text_parts)
        for tp in text_parts:
            holds_text.update(self.ancestors(tp))
        locked = {i for i in self.clean_locks(locks)
                  if i not in holds_text and not any(a in part_sw for a in self.ancestors(i))}
        pinned: set[int] = set(holds_text)
        for i in [*locked, *part_sw]:
            pinned.update(self.ancestors(i))

        def lit_seg(p: Part, si: int, seg: str) -> str:
            drop = p.id in dropping
            if not drop and not any(k.startswith(f"{p.id}.{si}.") for k in text_sw):
                return _lit(seg)
            out = []
            for k, (lead, core, trail) in enumerate(pieces(seg)):
                key = f"{p.id}.{si}.{k}"
                rep = text_sw.get(key)
                if rep is not None:
                    out.append(_lit(lead) + rep + _lit(trail))
                elif drop and core and key not in marked:
                    out.append(" ")  # left out; the punctuation pieces between picks stay
                else:
                    out.append(_lit(lead + core + trail))
            return "".join(out)

        def out(p: Part) -> str:
            if p.id in part_sw:
                return part_sw[p.id]
            if p.id in locked:
                return _lit(self.text_of(p))
            if p.id in pinned or p.id == 0:
                return "".join(lit_seg(p, si, s) if isinstance(s, str) else out(s) for si, s in enumerate(p.segs))
            return _src(p.source)

        text = out(self.root)
        if dropping:
            text = tidy(text)
        extra = " ".join(str(append or "").splitlines()).strip()[:MAX_SWAP]
        return f"{text.rstrip()} {extra}" if extra else text

    def leaves(self) -> list[int]:
        return [p.id for p in self.walk() if p.id != 0 and not self.children(p)]

    def reliable(self, lib: Library) -> bool:
        """Both self checks (module docstring)."""
        if self.fragile:
            return False
        if lib.expand(self.render([]), self.seed).text != self.prompt:
            return False
        return lib.expand(self.render(self.leaves()), 0).text == self.prompt

    # what the panel shows -------------------------------------------------------------------------------
    def view(self, p: Part | None = None) -> dict:
        p = p or self.root
        d = {"id": p.id, "kind": p.kind, "label": label(p), "src": _show(_src(p.source)) if p.id else "",
             "text": _show(self.text_of(p)), "group": group_of(p.name) if p.kind == "token" else None,
             "solo": is_solo(p), "missing": p.missing,
             "segs": [self._text_view(p, si, s) if isinstance(s, str) else self.view(s) for si, s in enumerate(p.segs)]}
        return d

    def _text_view(self, p: Part, si: int, seg: str) -> dict:
        """Literal text as pieces that can be replaced: ``{kind: "text", pieces: [{id, lead, core, trail}]}``."""
        return {"kind": "text", "pieces": [
            {"id": f"{p.id}.{si}.{k}", "lead": _show(a), "core": _show(c), "trail": _show(t)}
            for k, (a, c, t) in enumerate(pieces(seg))]}

    def groups(self) -> list[dict]:
        """Quick choices that have parts in this prompt: ``[{id, label, ids}]`` (outermost parts only)."""
        found: dict[str, list[int]] = {}
        for p in self.walk():
            g = group_of(p.name) if p.kind == "token" else None
            if g and not any(group_of(self.parts[a].name) == g and self.parts[a].kind == "token"
                             for a in self.ancestors(p.id)):
                found.setdefault(g, []).append(p.id)
        out = []
        for cid, (lab, members) in COMBINED.items():
            ids = [i for g in members for i in found.get(g, [])]
            if ids:
                out.append({"id": cid, "label": lab, "ids": sorted(ids)})
        for gid, lab, _rx in GROUPS:
            if found.get(gid):
                out.append({"id": gid, "label": lab, "ids": found[gid]})
        return out


# words (a . , or : between digits stays inside: 4:5, 1.5) | the punctuation after them
_PIECE_RE = re.compile(r"(?:[^,.;:!?\n]|(?<=\d)[.,:](?=\d))+|[,.;:!?\n]+")


def pieces(text: str) -> list[tuple[str, str, str]]:
    """Literal text -> ``(lead, core, trail)`` pieces, split after ``, . ; : ! ?`` and line breaks. ``core`` is the
    words, ``lead`` / ``trail`` the spaces and punctuation around them; joined, the pieces give ``text`` again."""
    out: list[tuple[str, str, str]] = []
    for m in _PIECE_RE.finditer(text):
        chunk = m.group(0)
        if chunk[0] in ",.;:!?\n":
            if out:
                lead, core, trail = out[-1]
                out[-1] = (lead, core, trail + chunk)
            else:
                out.append(("", "", chunk))
            continue
        core = chunk.strip()
        if not core:  # only spaces: they belong to the piece before
            if out:
                lead, c, trail = out[-1]
                out[-1] = (lead, c, trail + chunk)
            else:
                out.append((chunk, "", ""))
            continue
        lead = chunk[: len(chunk) - len(chunk.lstrip())]
        out.append((lead, core, chunk[len(chunk.rstrip()):]))
    return out


_SYNTAX_TOKEN = re.compile(r"__[\w.\-+/*\\ ]+?__")


def _protect(text: str) -> tuple[str, list[str]]:
    """Swap ``{…}`` groups (balanced, escapes skipped) and ``__tokens__`` for placeholders, so text edits never
    touch wildcard syntax."""
    held: list[str] = []
    out: list[str] = []
    i = 0
    while i < len(text):
        c = text[i]
        if c == "\\" and i + 1 < len(text):
            out.append(text[i:i + 2])
            i += 2
            continue
        if c == "{":
            depth, j = 0, i
            while j < len(text):
                if text[j] == "\\":
                    j += 2
                    continue
                depth += {"{": 1, "}": -1}.get(text[j], 0)
                j += 1
                if depth == 0:
                    break
            if depth == 0:
                held.append(text[i:j])
                out.append(f"{len(held) - 1}")
                i = j
                continue
        out.append(c)
        i += 1
    joined = "".join(out)

    def hold(m: re.Match) -> str:
        held.append(m.group(0))
        return f"{len(held) - 1}"

    return _SYNTAX_TOKEN.sub(hold, joined), held


def tidy(text: str) -> str:
    """Spaces and punctuation after text was left out: one space, no space before punctuation, no doubled,
    leading or trailing commas. Wildcard syntax is left as it is."""
    text, held = _protect(text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r" +([,.;:!?])", r"\1", text)
    text = re.sub(r"([,;:])(?:\s*[,;:])+", r"\1", text)
    text = re.sub(r"([.!?])(?:\s*[,;:.])+", r"\1", text)
    text = re.sub(r"[\s,;:]+$", "", text)
    text = re.sub(r"^[\s,.;:]+", "", text).strip()
    return re.sub("(\\d+)", lambda m: held[int(m.group(1))], text)


def is_plain(p: Part) -> bool:
    """A part whose own words are plain text (not a pick): the prompt, a template line, ``{x}``."""
    return p.kind == "root" or is_solo(p) or (p.kind == "token" and p.name.lower().startswith("templates/"))


def is_solo(p: Part) -> bool:
    """``{__x__}``: a group with one option and no count, which only wraps what is inside."""
    return p.kind == "options" and not _SOLO_SPLIT.search(p.name)


def label(p: Part) -> str:
    if p.kind == "root":
        return "prompt"
    if p.kind == "token":
        name = _show(p.name).strip().strip("/")
        return name.rsplit("/", 1)[-1] or name
    body = _show(p.name)
    if "$$" in body:
        return "several of"
    n = body.count("|") + 1
    return "one of" if n <= 1 else f"one of {n}"


def decompose(lib: Library, text: str, seed: int) -> Decomposition:
    """Expand ``text`` with ``seed`` again, with a record of every pick."""
    try:
        seed = int(seed)
    except (TypeError, ValueError):
        raise KeepError("KDX Keep parts: the seed is missing.") from None
    res = lib.expand(str(text or ""), seed, trace=True)
    if res.trace is None:  # pragma: no cover - expand(trace=True) always records
        raise KeepError("KDX Keep parts: no record of the expansion.")
    return Decomposition(str(text or ""), seed, res.text, res.missing, res.trace)


def compare(expected, prompt: str) -> bool | None:
    """Does the stored prompt match today's expansion? None when nothing was stored."""
    if not isinstance(expected, str) or not expected.strip():
        return None
    return expected.strip() == prompt.strip()

