"""Wildcards for KDX Wildcard Studio: the own engine (wildcard_engine.py) plus where the files are.

No other custom node is imported or called. The wildcard *files* are read from folders:

1. ``wildcard_dirs`` in config.json (set in the panel or via REST), else
2. the environment variable ``KDX_CONSOLE_WILDCARD_DIRS`` (paths separated by ``os.pathsep``), else
3. ``<ComfyUI user dir>/kdx_console/wildcards`` when it holds at least one ``.txt`` file — the
   recommended place: it sits next to config.json/state.json and is backed up with the user folder, else
4. the folders that exist among: ``<custom_nodes>/comfyui-impact-pack/custom_wildcards``,
   ``<custom_nodes>/comfyui-impact-pack/wildcards`` and ``<ComfyUI>/wildcards``. Only the files
   are read there; the pack itself does not have to be installed or loaded.

The library reloads by itself when a file is added, removed or changed.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
from typing import Callable

from .engine import TEMPLATE_PREFIX, ConsoleError
from .wildcard_engine import CachedLibrary, Library

log = logging.getLogger("KDX-Wildcard-Studio")

ENV_DIRS = "KDX_CONSOLE_WILDCARD_DIRS"
#: Template names that are never listed, imported or offered (NSFW content is out of scope).
EXCLUDED_PREFIXES = ("nsfw", "akt", "sheer")

_PACK_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CUSTOM_NODES_DIR = os.path.dirname(_PACK_DIR)
COMFY_DIR = os.path.dirname(CUSTOM_NODES_DIR)

USER_SUBDIR = "wildcards"

_cache = CachedLibrary()
_dirs_provider: Callable[[], list] | None = None
_user_root_provider: Callable[[], str] | None = None
_last_missing: list[str] = []


def set_dirs_provider(fn: Callable[[], list] | None) -> None:
    """Where the configured folders come from (the node wires this to config.json)."""
    global _dirs_provider
    _dirs_provider = fn


def set_user_root_provider(fn: Callable[[], str] | None) -> None:
    """KDX Wildcard Studio's data folder (``<user dir>/kdx_console``); wildcards live in its ``wildcards/``."""
    global _user_root_provider
    _user_root_provider = fn


def user_wildcard_dir() -> str | None:
    if _user_root_provider is None:
        return None
    try:
        return os.path.join(_user_root_provider(), USER_SUBDIR)
    except Exception as e:
        log.warning("[KDX-Wildcard-Studio] user folder not available: %s", e)
        return None


def _has_txt(root: str) -> bool:
    for _dirpath, _dirs, files in os.walk(root, followlinks=True):
        if any(f.lower().endswith(".txt") for f in files):
            return True
    return False


def _impact_dir() -> str | None:
    try:
        for name in os.listdir(CUSTOM_NODES_DIR):
            if name.lower() == "comfyui-impact-pack":
                return os.path.join(CUSTOM_NODES_DIR, name)
    except OSError:
        pass
    return None


STARTER_DIR = os.path.join(_PACK_DIR, "starter_wildcards")


def install_starter() -> str | None:
    """First start: copy the bundled example library to ``<user dir>/kdx_console/wildcards``.

    Only when nothing would be found otherwise: no folders set by the user (config/env), the user folder
    has no ``.txt`` files and no other automatic folder has any. Returns the target folder or ``None``."""
    user = user_wildcard_dir()
    if not user or not os.path.isdir(STARTER_DIR):
        return None
    dirs, src = resolve_dirs()
    if src != "auto" or any(os.path.isdir(d) and _has_txt(d) for d in dirs):
        return None
    shutil.copytree(STARTER_DIR, user, dirs_exist_ok=True)
    log.info("[KDX-Wildcard-Studio] starter wildcard library copied to %s", user)
    return user


def automatic_dirs() -> list[str]:
    user = user_wildcard_dir()
    if user and os.path.isdir(user) and _has_txt(user):
        return [user]
    cands = []
    pack = _impact_dir()
    if pack:
        cands += [os.path.join(pack, "custom_wildcards"), os.path.join(pack, "wildcards")]
    cands.append(os.path.join(COMFY_DIR, "wildcards"))
    return [d for d in cands if os.path.isdir(d)]


def resolve_dirs(configured=None) -> tuple[list[str], str]:
    """``(folders, source)``; source is ``config``, ``env`` or ``auto``."""
    if configured is None and _dirs_provider is not None:
        try:
            configured = _dirs_provider()
        except Exception as e:  # a broken config must not hide the wildcards
            log.warning("[KDX-Wildcard-Studio] wildcard_dirs not readable: %s", e)
            configured = None
    if configured:
        return [os.path.expanduser(str(d)) for d in configured], "config"
    env = os.environ.get(ENV_DIRS, "").strip()
    if env:
        return [d for d in env.split(os.pathsep) if d.strip()], "env"
    return automatic_dirs(), "auto"


def library(configured=None) -> Library:
    dirs, _src = resolve_dirs(configured)
    return _cache.get(dirs)


def expand(text: str, seed: int) -> str:
    """Expand wildcards in ``text`` with ``seed`` (same text + seed = same result)."""
    lib = library()
    if not lib.data:
        dirs, src = resolve_dirs()
        raise ConsoleError(
            "KDX Wildcard Studio: no wildcard files found "
            f"({src} folders: {', '.join(dirs) or 'none'}). Set the wildcard folders in the panel.")
    res = lib.expand(text, seed)
    _last_missing[:] = res.missing
    if res.missing:
        log.warning("[KDX-Wildcard-Studio] unknown wildcards left in the prompt: %s", ", ".join(res.missing))
    return res.text


def info(configured=None) -> dict:
    """What the panel shows about the wildcard library."""
    dirs, src = resolve_dirs(configured)
    lib = _cache.get(dirs)
    keys = lib.keys()
    return {
        "dirs": dirs,
        "source": src,
        "user_dir": user_wildcard_dir(),
        "missing_dirs": [d for d in dirs if not os.path.isdir(d)],
        "files": len(keys),
        "templates": len(filter_templates(keys)),
        "duplicates": len(lib.duplicates),
        "last_missing": list(_last_missing),
    }


_WORD_SPLIT = re.compile(r"[/\\_\-\s.]+")


def is_excluded(name: str) -> bool:
    """An NSFW name: a word of it (split at ``/ _ - .``) starts with nsfw, akt or sheer, so ``nsfw_detail``,
    ``akt_back`` and ``outdoor_nsfw`` all count."""
    return any(w.startswith(EXCLUDED_PREFIXES) for w in _WORD_SPLIT.split(str(name or "").lower()) if w)


def filter_templates(keys, *, include_excluded: bool = False) -> list[str]:
    """``["templates/portrait", "__templates/selfie__", "core/x", ...]`` -> ``["portrait", "selfie"]``
    (safe templates only unless ``include_excluded``; order preserved, duplicates dropped)."""
    out: list[str] = []
    for k in keys or []:
        s = str(k).strip()
        if s.startswith("__") and s.endswith("__"):
            s = s[2:-2]
        if not s.startswith(TEMPLATE_PREFIX):
            continue
        name = s[len(TEMPLATE_PREFIX):]
        if not name or (is_excluded(name) and not include_excluded) or name in out:
            continue
        out.append(name)
    return out


def list_templates(include_excluded: bool = False) -> list[str]:
    """Template names in the wildcard folders right now (sorted); NSFW ones only with include_excluded."""
    return sorted(filter_templates(library().keys(), include_excluded=include_excluded))


def list_all_templates() -> list[str]:
    """Every template name that has a file, excluded ones included (sorted). Import uses it to tell a
    template that is only hidden from auto-import from one whose file is really gone."""
    return sorted(filter_templates(library().keys(), include_excluded=True))
