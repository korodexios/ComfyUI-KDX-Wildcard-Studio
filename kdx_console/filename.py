"""File-name prefix from a pattern (pure, no ComfyUI): ``%template%_%date:yyyyMMdd_hhmmss%`` -> ``outdoor_20261119_143005``.

ComfyUI replaces ``%date:...%`` only in the widget of a Save node, in the browser, before the prompt is sent. A
prefix that arrives over a wire is never touched, and node *outputs* (the template that is running now) are unknown
to the browser anyway. So the pattern is resolved here, at run time, with the data of the run.

Tokens:
  ``%key%``            value of ``key`` in the JSON (``template``, ``category``, ``seed``, ``index``, ...);
                       ``%a.b%`` reads nested objects, ``%list.0%`` list items
  ``%date:format%``    local time, ComfyUI letters: yyyy yy MM dd hh mm ss (``M d h m s`` = no zero padding)
  ``%width%``/``%height%``  left untouched: ComfyUI's Save node fills them in itself

Values are made safe for a file name (``/ \\ : * ? " < > |`` -> ``_``); folders come only from ``/`` in the pattern.
"""

from __future__ import annotations

import json
import re
from datetime import datetime

LEAVE_ALONE = ("width", "height")  # replaced later by ComfyUI's SaveImage
_TOKEN = re.compile(r"%([^%\r\n]+)%")
_BAD = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')
_DATE_RUN = {"d": "day", "M": "month", "h": "hour", "m": "minute", "s": "second"}


class FilenameError(ValueError):
    """User-facing problem (shown in the ComfyUI error dialog as is)."""


def safe(value) -> str:
    """One value as a file-name piece."""
    if isinstance(value, bool):
        s = "true" if value else "false"
    elif isinstance(value, (dict, list)):
        s = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    else:
        s = "" if value is None else str(value)
    s = _BAD.sub("_", s).strip().strip(".")
    return s.replace("..", ".")


def format_date(fmt: str, now: datetime) -> str:
    """ComfyUI-style date format. ``yyyy``/``yy`` first, then runs of ``M d h m s``."""
    out = fmt.replace("yyyy", f"{now.year:04d}").replace("yy", f"{now.year % 100:02d}")
    parts = {"d": now.day, "M": now.month, "h": now.hour, "m": now.minute, "s": now.second}
    for letter, number in parts.items():
        out = re.sub(f"{letter}+", lambda m, n=number: str(n).rjust(len(m.group(0)), "0"), out)
    return safe(out)


def parse_data(text) -> dict:
    """The JSON of the run (an object). Empty text -> {} so the pattern can still use ``%date%``."""
    if isinstance(text, dict):
        return text
    s = str(text or "").strip()
    if not s:
        return {}
    try:
        data = json.loads(s)
    except ValueError as e:
        raise FilenameError(f"KDX Filename: state_json is not valid JSON ({e}).") from None
    if not isinstance(data, dict):
        raise FilenameError("KDX Filename: state_json must be a JSON object.")
    return data


def lookup(data: dict, path: str):
    """``a.b.0`` -> data['a']['b'][0]; a plain key wins over a dotted path. Raises KeyError."""
    if path in data:
        return data[path]
    low = {str(k).lower(): k for k in data}
    if path.lower() in low:
        return data[low[path.lower()]]
    cur = data
    for part in path.split("."):
        if isinstance(cur, dict):
            if part in cur:
                cur = cur[part]
                continue
            hit = {str(k).lower(): k for k in cur}.get(part.lower())
            if hit is None:
                raise KeyError(path)
            cur = cur[hit]
        elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            raise KeyError(path)
    return cur


def build(pattern: str, data: dict, now: datetime | None = None) -> str:
    """Resolve ``pattern`` with ``data``. Unknown keys raise, listing what is available."""
    now = now or datetime.now()
    pattern = str(pattern or "").strip()
    if not pattern:
        raise FilenameError("KDX Filename: the pattern is empty.")

    def repl(m: re.Match) -> str:
        token = m.group(1).strip()
        if token.lower().startswith("date:"):
            return format_date(token[5:], now)
        if token.lower() == "date":
            return format_date("yyyyMMdd_hhmmss", now)
        if token.lower() in LEAVE_ALONE:
            return m.group(0)
        try:
            return safe(lookup(data, token))
        except KeyError:
            known = ", ".join(sorted(str(k) for k in data)) or "(none: connect state_json)"
            raise FilenameError(f"KDX Filename: unknown %{token}% in the pattern. Available: {known}, date:<format>.") from None

    out = _TOKEN.sub(repl, pattern)
    # tidy: no empty path parts, no leading slash (the output folder is fixed by ComfyUI)
    parts = [p.strip() for p in out.replace("\\", "/").split("/")]
    out = "/".join(p for p in parts if p and p != "..")
    if not out:
        raise FilenameError("KDX Filename: the pattern produced an empty name.")
    return out
