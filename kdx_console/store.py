"""Persistent config/state for KDX Wildcard Studio (no ComfyUI imports).

Files in ``<root>`` (default ``<ComfyUI user dir>/kdx_console``):
  * ``config.json`` — written by the user (panel / REST)
  * ``state.json``  — written by the engine (cursor per channel)

Writes are atomic (tmp + fsync + ``os.replace``) and serialized by one lock. A file that
cannot be parsed is copied to ``<name>.bak`` and replaced by defaults.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import threading
import time
from dataclasses import dataclass
from typing import Callable

from . import engine
from . import overrides as ov_mod
from . import scope as scope_mod
from .engine import DEFAULT_CHANNEL, ConsoleError, Pin

log = logging.getLogger("KDX-Wildcard-Studio")

CONFIG_FILE = "config.json"
STATE_FILE = "state.json"

Expander = Callable[[str, int], str]  # (template token, seed) -> prompt
Listener = Callable[[str, dict], None]  # (event kind, payload)


def default_root() -> str:
    env = os.environ.get("KDX_CONSOLE_DIR", "").strip()
    if env:
        return os.path.expanduser(env)
    try:
        import folder_paths  # type: ignore

        return os.path.join(folder_paths.get_user_directory(), "kdx_console")
    except Exception:
        return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "user_data")


@dataclass
class RunResult:
    plan: engine.Plan
    prompt: str
    system_prompt_text: str
    state: dict  # channel state after the run
    warnings: list[str]

    @property
    def used(self) -> dict:
        d = self.plan.to_dict()
        d["time"] = time.time()
        return d


class Store:
    def __init__(self, root: str | None = None, seed_fn: engine.SeedFn = engine.random_seed):
        self.root = root or default_root()
        self.seed_fn = seed_fn
        self.lock = threading.RLock()
        self.listeners: list[Listener] = []
        self.last_warnings: list[str] = []

    # ------------------------------------------------------------------ files
    @property
    def config_path(self) -> str:
        return os.path.join(self.root, CONFIG_FILE)

    @property
    def state_path(self) -> str:
        return os.path.join(self.root, STATE_FILE)

    def _write_json(self, path: str, data: dict) -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass

    def _read_json(self, path: str):
        """Parsed JSON, ``None`` when missing; corrupt/foreign files are backed up and give ``None``."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            return None
        except (OSError, ValueError, UnicodeDecodeError) as e:
            self._backup(path, f"unreadable file ({e})")
            return None
        if not isinstance(data, dict):
            self._backup(path, "not a JSON object")
            return None
        ver = data.get("schema_version", engine.SCHEMA_VERSION)
        if ver != engine.SCHEMA_VERSION:
            self._backup(path, f"schema_version {ver!r} != {engine.SCHEMA_VERSION}")
            return None
        return data

    def _backup(self, path: str, why: str) -> None:
        bak = path + ".bak"
        try:
            shutil.copyfile(path, bak)
        except OSError:
            pass
        msg = f"{os.path.basename(path)}: {why}; backup {os.path.basename(bak)}, defaults used"
        log.warning("[KDX-Wildcard-Studio] %s", msg)
        self.last_warnings.append(msg)

    # ------------------------------------------------------------------ load / save
    def load_config(self) -> dict:
        with self.lock:
            raw = self._read_json(self.config_path)
            cfg, warns = engine.normalize_config(raw)
            if raw is None and os.path.exists(self.config_path):
                # corrupt -> persist defaults; the .bak keeps the bad file
                self._write_json(self.config_path, cfg)
            for w in warns:
                log.warning("[KDX-Wildcard-Studio] config: %s", w)
            return cfg

    def load_state(self) -> dict:
        with self.lock:
            raw = self._read_json(self.state_path)
            state, warns = engine.normalize_state(raw, self.seed_fn)
            missing = DEFAULT_CHANNEL not in state["channels"]
            if missing:  # persist the channel so its next_seed is the same for preview and run
                engine.get_channel(state, DEFAULT_CHANNEL, self.seed_fn)
            if missing or (raw is None and os.path.exists(self.state_path)):
                self._write_json(self.state_path, state)
            for w in warns:
                log.warning("[KDX-Wildcard-Studio] state: %s", w)
            return state

    def save_config(self, raw: dict) -> tuple[dict, list[str]]:
        """Validate and store a new config; the cursor is re-validated against it."""
        with self.lock:
            cfg, warns = engine.normalize_config(raw)
            self._write_json(self.config_path, cfg)
            state = self.load_state()
            changed = False
            for ch in state["channels"].values():
                if not engine.any_enabled(cfg) or ch.get("category") is None:
                    continue
                ci, ti, done = engine.locate(cfg, ch)
                before = (ch["category"], ch["template"], ch["done"])
                engine._set_cursor(ch, cfg, ci, ti, done)
                changed |= before != (ch["category"], ch["template"], ch["done"])
            if changed:
                self._write_json(self.state_path, state)
        self._emit("config", {"config": cfg, "warnings": warns})
        if changed:
            self._emit_state(state)
        return cfg, warns

    def save_state(self, state: dict) -> None:
        with self.lock:
            self._write_json(self.state_path, state)
        self._emit_state(state)

    # ------------------------------------------------------------------ events
    def _emit(self, kind: str, payload: dict) -> None:
        for fn in list(self.listeners):
            try:
                fn(kind, payload)
            except Exception as e:  # a broken listener must never break a run
                log.warning("[KDX-Wildcard-Studio] listener failed: %s", e)

    def notify_finished(self, message: str) -> None:
        """Tell the panel that a run was skipped because the category is finished (on_end = stop)."""
        self._emit("finished", {"message": message})

    def _emit_state(self, state: dict) -> None:
        self._emit("state", {"state": state})

    # ------------------------------------------------------------------ run
    def effective(self, overrides: str = "", scope: str = "") -> tuple[dict, dict, ov_mod.Overrides]:
        """Config for one run: shared config -> workflow scope (on/off) -> overrides (wins)."""
        cfg = self.load_config()
        state = self.load_state()
        ov = ov_mod.parse(overrides)
        cfg = scope_mod.apply(cfg, scope_mod.parse(scope))
        return ov_mod.apply(cfg, ov), state, ov

    @staticmethod
    def channel_of(scope: str = "", channel: str | None = None) -> str:
        return channel or scope_mod.parse(scope).channel

    def fingerprint(self, overrides: str = "", pin: str = "", channel: str | None = None, scope: str = "") -> str:
        channel = self.channel_of(scope, channel)
        with self.lock:
            cfg = scope_mod.apply(self.load_config(), scope_mod.parse(scope))
            state = self.load_state()
        return engine.fingerprint(cfg, state, channel=channel, overrides=overrides or "", pin=pin or "")

    def plan(self, overrides: str = "", pin: str = "", channel: str | None = None, scope: str = "") -> engine.Plan:
        channel = self.channel_of(scope, channel)
        with self.lock:
            cfg, state, ov = self.effective(overrides, scope)
            return engine.plan(cfg, state, channel=channel, mode=ov.mode, select=ov.select, seed=ov.seed,
                               pin=Pin.parse(pin), seed_fn=self.seed_fn)

    def run(self, expand: Expander, *, overrides: str = "", pin: str = "", channel: str | None = None,
            scope: str = "", resolve_system_prompt: Callable[[str], str] | None = None) -> RunResult:
        """Plan -> expand -> commit, all under the lock. The counter moves only when
        ``expand`` succeeded and returned a usable prompt."""
        channel = self.channel_of(scope, channel)
        with self.lock:
            self.last_warnings = []
            cfg, state, ov = self.effective(overrides, scope)
            p = engine.plan(cfg, state, channel=channel, mode=ov.mode, select=ov.select, seed=ov.seed,
                            pin=Pin.parse(pin), seed_fn=self.seed_fn)
            text = expand(p.token, p.seed)
            if not isinstance(text, str) or not text.strip():
                raise ConsoleError(f"KDX Wildcard Studio: template '{p.template}' expanded to empty text.")
            if p.token in text:
                raise ConsoleError(
                    f"KDX Wildcard Studio: template '{p.template}' does not exist in the wildcards "
                    f"({p.token} was not expanded). Check templates/{p.template}.txt in the wildcard folders "
                    "(KDX Wildcard Studio panel › Wildcards).")
            sp_text = ""
            if p.llm_enabled and p.system_prompt and resolve_system_prompt is not None:
                sp_text = resolve_system_prompt(p.system_prompt)
            result = RunResult(plan=p, prompt=text, system_prompt_text=sp_text, state={},
                               warnings=list(self.last_warnings))
            new_state = engine.commit(cfg, state, p, last=result.used, seed_fn=self.seed_fn)
            self._write_json(self.state_path, new_state)
            result.state = new_state["channels"][channel]
        self._emit_state(new_state)
        self._emit("run", {"used": result.used})
        return result

    # ------------------------------------------------------------------ actions
    def reset(self, channel: str | None = None, scope: str = "") -> dict:
        channel = self.channel_of(scope, channel)
        with self.lock:
            state = engine.reset(self.load_state(), channel, self.seed_fn)
            self._write_json(self.state_path, state)
        self._emit_state(state)
        return state

    def skip(self, channel: str | None = None, overrides: str = "", scope: str = "") -> dict:
        channel = self.channel_of(scope, channel)
        with self.lock:
            cfg, state, _ = self.effective(overrides, scope)
            state = engine.skip(cfg, state, channel, self.seed_fn)
            self._write_json(self.state_path, state)
        self._emit_state(state)
        return state

    def select(self, category: str, template: str, channel: str | None = None, scope: str = "") -> dict:
        channel = self.channel_of(scope, channel)
        with self.lock:
            cfg = scope_mod.apply(self.load_config(), scope_mod.parse(scope))
            state = engine.select_cursor(cfg, self.load_state(), category, template, channel, self.seed_fn)
            self._write_json(self.state_path, state)
        self._emit_state(state)
        return state

    def preview(self, overrides: str = "", pin: str = "", channel: str | None = None, count: int = 5,
                scope: str = "") -> dict:
        with self.lock:
            try:
                channel = self.channel_of(scope, channel)
                cfg, state, ov = self.effective(overrides, scope)
                p = Pin.parse(pin)
            except ConsoleError as e:
                return {"upcoming": [], "error": str(e)}
            return engine.preview(cfg, state, count=count, channel=channel, mode=ov.mode, select=ov.select,
                                  seed=ov.seed, pin=p)
