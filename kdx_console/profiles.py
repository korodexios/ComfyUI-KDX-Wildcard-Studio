"""Read-only access to KDX-LLM system prompts (no import of KDX-LLM).

KDX-LLM 0.10+ keeps one text file per prompt in ``<ComfyUI user dir>/kdx_llm/system_prompts/``
(``<name>.md`` or ``<name>.txt``; ``$KDX_LLM_PROMPTS_DIR`` overrides the folder). The file holds the
prompt text as written; the file name is the profile name.

Older KDX-LLM versions used one ``system_prompts.json`` (``$KDX_LLM_PROMPTS_FILE``); it is still read
for names that have no file yet, so nothing breaks before KDX-LLM migrates it.
"""

from __future__ import annotations

import json
import os

from .engine import ConsoleError

EXTENSIONS = (".md", ".txt")


def _user_base() -> str:
    try:
        import folder_paths  # type: ignore

        return os.path.join(folder_paths.get_user_directory(), "kdx_llm")
    except Exception:
        return ""


def legacy_path() -> str:
    env = os.environ.get("KDX_LLM_PROMPTS_FILE", "").strip()
    if env:
        return os.path.expanduser(env)
    base = _user_base()
    return os.path.join(base, "system_prompts.json") if base else ""


def prompts_dir() -> str:
    env = os.environ.get("KDX_LLM_PROMPTS_DIR", "").strip()
    if env:
        return os.path.expanduser(env)
    if os.environ.get("KDX_LLM_PROMPTS_FILE", "").strip():
        return os.path.splitext(legacy_path())[0]
    base = _user_base()
    return os.path.join(base, "system_prompts") if base else ""


def _files(folder: str) -> dict[str, str]:
    found: dict[str, str] = {}
    try:
        entries = sorted(os.listdir(folder))
    except OSError:
        return found
    for fn in entries:
        stem, ext = os.path.splitext(fn)
        if fn.startswith(".") or not stem or ext.lower() not in EXTENSIONS:
            continue
        path = os.path.join(folder, fn)
        if os.path.isfile(path) and not (stem in found and found[stem].lower().endswith(".md")):
            found[stem] = path
    return found


def _legacy(path: str) -> dict:
    if not path:
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    prompts = data.get("prompts", data) if isinstance(data, dict) else {}
    return prompts if isinstance(prompts, dict) else {}


def names(folder: str | None = None, legacy: str | None = None) -> list[str]:
    folder = prompts_dir() if folder is None else folder
    legacy = legacy_path() if legacy is None else legacy
    return sorted(set(_files(folder)) | set(_legacy(legacy)))


def resolve(name: str, folder: str | None = None, legacy: str | None = None) -> str:
    """Prompt text of profile ``name``; empty name -> ''. Unknown name -> ConsoleError."""
    name = (name or "").strip()
    if not name:
        return ""
    folder = prompts_dir() if folder is None else folder
    path = _files(folder).get(name)
    if path:
        with open(path, "r", encoding="utf-8-sig", errors="replace", newline="") as f:
            return f.read()
    value = _legacy(legacy_path() if legacy is None else legacy).get(name)
    if isinstance(value, dict):
        return str(value.get("prompt") or "")
    if isinstance(value, str):
        return value
    raise ConsoleError(
        f"KDX Wildcard Studio: system prompt '{name}' was not found (KDX-LLM folder {folder or 'kdx_llm/system_prompts'}). "
        "Pick another one in the panel or turn LLM off.")
