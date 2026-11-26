"""Gallery: find the images KDX Wildcard Studio made, with what made them (pure logic, no ComfyUI imports).

Every image saved after a KDX Wildcard Studio run carries a ``kdx_console`` text chunk (see ``embed.py``): category,
template, seed and, since 0.6.9, the expanded prompt. The gallery walks an output folder, reads only the PNG
header chunks (never the pixels), and returns the newest images first. Results are cached per file
(path + mtime + size), so opening the gallery again reads only new files.
"""

from __future__ import annotations

import json
import os
import struct
import threading
import zlib

PNG_SIG = b"\x89PNG\r\n\x1a\n"
META_KEY = "kdx_console"
DEFAULT_LIMIT = 600
MAX_LIMIT = 5000
MAX_CHUNK = 32 * 1024 * 1024  # a text chunk larger than this is not ours; stop reading


def read_png_text(path: str) -> tuple[dict[str, str], tuple[int, int] | None]:
    """Text chunks (tEXt, zTXt, iTXt) and (width, height) of a PNG, read up to the first IDAT chunk.

    Returns ``({}, None)`` for a file that is not a PNG or cannot be read."""
    texts: dict[str, str] = {}
    size = None
    try:
        with open(path, "rb") as f:
            if f.read(8) != PNG_SIG:
                return {}, None
            while True:
                head = f.read(8)
                if len(head) < 8:
                    break
                length, ctype = struct.unpack(">I4s", head)
                if ctype == b"IDAT" or ctype == b"IEND" or length > MAX_CHUNK:
                    break
                data = f.read(length)
                f.read(4)  # CRC
                if ctype == b"IHDR" and len(data) >= 8:
                    size = struct.unpack(">II", data[:8])
                elif ctype == b"tEXt":
                    k, _, v = data.partition(b"\0")
                    texts[k.decode("latin-1")] = v.decode("latin-1")
                elif ctype == b"zTXt":
                    k, _, rest = data.partition(b"\0")
                    try:
                        texts[k.decode("latin-1")] = zlib.decompress(rest[1:]).decode("latin-1")
                    except zlib.error:
                        pass
                elif ctype == b"iTXt":
                    k, _, rest = data.partition(b"\0")
                    if len(rest) < 2:
                        continue
                    compressed = rest[0] == 1
                    rest = rest[2:]
                    _lang, _, rest = rest.partition(b"\0")
                    _tkey, _, value = rest.partition(b"\0")
                    try:
                        value = zlib.decompress(value) if compressed else value
                        texts[k.decode("latin-1")] = value.decode("utf-8")
                    except (zlib.error, UnicodeDecodeError):
                        pass
    except OSError:
        return {}, None
    return texts, size


def _fix_text(s: str) -> str:
    """ComfyUI writes tEXt (latin-1) chunks with UTF-8 bytes in them: undo the double decoding."""
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def _longest_input(prompt_json: str) -> str:
    """Fallback for images made before 0.6.9: the longest string input of the saved prompt graph."""
    best = ""
    try:
        graph = json.loads(prompt_json)
    except (ValueError, TypeError):
        return ""
    if not isinstance(graph, dict):
        return ""
    for node in graph.values():
        inputs = node.get("inputs") if isinstance(node, dict) else None
        for v in (inputs or {}).values():
            if isinstance(v, str) and len(v) > len(best):
                best = v
    return best if len(best) > 80 else ""


def image_meta(path: str) -> dict | None:
    """What KDX Wildcard Studio wrote into this image, or None when the image is not ours."""
    texts, size = read_png_text(path)
    raw = texts.get(META_KEY)
    if not raw:
        return None
    try:
        used = json.loads(_fix_text(raw))
    except ValueError:
        return None
    if not isinstance(used, dict) or not used.get("template"):
        return None
    prompt = used.get("prompt")
    if not isinstance(prompt, str) or not prompt:
        prompt = _longest_input(_fix_text(texts.get("prompt", "")))
    out = {
        "template": str(used.get("template")),
        "category": str(used.get("category") or ""),
        "category_name": str(used.get("category_name") or used.get("category") or ""),
        "seed": used.get("seed"),
        "index": used.get("index"),
        "repeat": used.get("repeat"),
        "mode": used.get("mode"),
        "prompt": prompt,
    }
    if size:
        out["width"], out["height"] = size
    return out


class Gallery:
    """Scanner with a per-file cache (thread-safe; the aiohttp handler runs it in a worker thread)."""

    def __init__(self) -> None:
        self._cache: dict[str, tuple[float, int, dict | None]] = {}
        self._lock = threading.Lock()

    def scan(self, root: str, since: float = 0.0, limit: int = DEFAULT_LIMIT, category: str = "",
             template: str = "") -> dict:
        """Newest KDX Wildcard Studio images under ``root`` (newer than ``since``, epoch seconds).

        ``category`` / ``template`` filter by exact key / name. Returns ``{"items": [...], "more": bool}``;
        every item has ``filename``, ``subfolder``, ``type`` (``output``), ``time`` and the fields of
        :func:`image_meta`."""
        limit = max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))
        files: list[tuple[float, int, str, str]] = []
        root = os.path.abspath(root)
        for dirpath, _dirs, names in os.walk(root):
            for name in names:
                if not name.lower().endswith(".png"):
                    continue
                path = os.path.join(dirpath, name)
                try:
                    st = os.stat(path)
                except OSError:
                    continue
                if st.st_mtime < since:
                    continue
                files.append((st.st_mtime, st.st_size, path, name))
        files.sort(reverse=True)
        items: list[dict] = []
        more = False
        seen: set[str] = set()
        for mtime, fsize, path, name in files:
            seen.add(path)
            meta = self._meta(path, mtime, fsize)
            if not meta:
                continue
            if category and meta["category"] != category:
                continue
            if template and meta["template"] != template:
                continue
            if len(items) >= limit:
                more = True
                break
            sub = os.path.relpath(os.path.dirname(path), root)
            items.append({"filename": name, "subfolder": "" if sub == "." else sub.replace(os.sep, "/"),
                          "type": "output", "time": mtime, **meta})
        with self._lock:  # forget files that were deleted, so the cache does not grow forever
            if since <= 0 and not category and not template:
                for p in [p for p in self._cache if p not in seen and p.startswith(root)]:
                    del self._cache[p]
        return {"items": items, "more": more}

    def _meta(self, path: str, mtime: float, fsize: int) -> dict | None:
        with self._lock:
            hit = self._cache.get(path)
        if hit and hit[0] == mtime and hit[1] == fsize:
            return hit[2]
        meta = image_meta(path)
        with self._lock:
            self._cache[path] = (mtime, fsize, meta)
        return meta


GALLERY = Gallery()


def parse_query(q: dict) -> dict:
    """Query string of ``GET /kdx_console/gallery`` -> keyword arguments of :meth:`Gallery.scan`."""

    def num(key: str, default: float) -> float:
        try:
            return float(q.get(key, default))
        except (TypeError, ValueError):
            return default

    return {"since": max(0.0, num("since", 0.0)), "limit": int(num("limit", DEFAULT_LIMIT)),
            "category": str(q.get("category") or "").strip(), "template": str(q.get("template") or "").strip()}
