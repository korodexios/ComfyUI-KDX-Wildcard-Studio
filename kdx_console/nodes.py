"""ComfyUI node ``KDX_Console`` (V1 API). Settings live in the panel/REST, not in widgets.

Inputs (positional ``widgets_values`` — never rename/reorder, new ones only at the end):
  * ``pin``        STRING widget (hidden by the panel JS). Empty = normal run. Filled
                   automatically in the *image's* copy of the workflow, so dragging the
                   image back reproduces the same prompt.
  * ``overrides``  optional STRING socket for remote control (SetNode/GetNode).
  * ``scope``      STRING widget (hidden): this workflow's own on/off and counter.
  * ``user_prompt`` optional STRING socket: a connected, non-empty text replaces the template prompt.
                   A muted or bypassed source node sends nothing, so the Studio prompt is used again.
  * ``user_text`` / ``use_user_text``  the same typed into the node itself, used only while the switch is on.
  * ``user_system_prompt``  combo widget: the KDX-LLM profile sent with the user's own text while LLM is on.

User text may hold wildcards (``__core/light_sky__``, ``{a|b}``); they are expanded with a fresh seed. The
template counter does not move. The LLM switch (panel or ``llm=`` override) applies as for templates; the
system prompt comes from ``user_system_prompt`` because the text belongs to no category. The image records the
text and the seed (pin ``{"user": true, "seed": ...}``), so dragging it back gives the same prompt.
"""

from __future__ import annotations

import hashlib
import json
import logging

from . import embed, filename, profiles, wildcards
from .engine import ConsoleError, ConsoleFinished, Pin, random_seed
from .store import Store

log = logging.getLogger("KDX-Wildcard-Studio")

USER_TEMPLATE = "user_prompt"
USER_CATEGORY = "user"
NO_PROFILE = "(no system prompt)"
_WILDCARD_SYNTAX = ("__", "{")

_STORE: Store | None = None


def get_store() -> Store:
    global _STORE
    if _STORE is None:
        _STORE = Store()
    return _STORE


# The wildcard engine reads its folders from config.json (empty = automatic).
wildcards.set_dirs_provider(lambda: get_store().load_config().get("wildcard_dirs") or [])
# Recommended home of the wildcard files: <ComfyUI user dir>/kdx_wildcard_studio/wildcards.
wildcards.set_user_root_provider(lambda: get_store().root)


def _summary(plan) -> str:
    if plan.mode == "sequential":
        pos = f"{plan.index}/{plan.repeat}"
    elif plan.mode == "pin":
        pos = f"pin #{plan.index}"
    else:
        pos = "manual"
    return f"{plan.category_name} › {plan.template} · {pos} · seed {plan.seed}"


class KDX_Console:
    CATEGORY = "KDX/Wildcard Studio"
    FUNCTION = "run"
    DESCRIPTION = ("Control centre for wildcard templates: every successful Run advances a server-side counter "
                   "(categories, repeat, on_end). Settings live in the KDX Wildcard Studio side panel.")
    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "INT", "INT", "BOOLEAN", "STRING")
    RETURN_NAMES = ("prompt", "system_prompt", "category", "template", "index", "repeat_left", "llm_enabled",
                    "state_json")
    OUTPUT_TOOLTIPS = (
        "Expanded template prompt",
        "System prompt text (KDX-LLM profile of the category, or user_system_prompt for your own text); "
        "empty when LLM is off",
        "Category key",
        "Template name (templates/<name>)",
        "Image number within the template repeat (from 1)",
        "Images left for this template",
        "LLM switch from the panel or overrides (True = LLM on). Connect to llm_enabled of KDX-LLM Chat (0.9.0+)",
        "Used state as JSON",
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "pin": ("STRING", {"default": "", "multiline": False,
                                   "tooltip": "Internal: exact reproduction from an image. Empty = normal run."}),
            },
            "optional": {
                "overrides": ("STRING", {"forceInput": True,
                                         "tooltip": "e.g. art=off, portrait.selfie=on, select=art.cubism"}),
                "scope": ("STRING", {"default": "", "multiline": False,
                                     "tooltip": "Internal: this workflow's own on/off and counter (set in the panel). "
                                                "Empty = shared settings."}),
                "user_prompt": ("STRING", {"forceInput": True,
                                           "tooltip": "Your own prompt from a text node. Connected and not empty = "
                                                      "used instead of the template (wildcards allowed). Mute or "
                                                      "bypass the text node to go back to the Studio prompt."}),
                "user_text": ("STRING", {"default": "", "multiline": True,
                                         "placeholder": "Your own prompt (used while the switch below is on)",
                                         "tooltip": "Your own prompt typed here; used only while use_user_text "
                                                    "is on. Wildcards allowed. A connected user_prompt wins."}),
                "use_user_text": ("BOOLEAN", {"default": False, "label_on": "user text", "label_off": "templates",
                                              "tooltip": "On = use the text above instead of the template."}),
                "user_system_prompt": ([NO_PROFILE, *profiles.names()],
                                       {"default": NO_PROFILE,
                                        "tooltip": "KDX-LLM system prompt for your own prompt (user_text or "
                                                   "user_prompt) while LLM is on. Templates use their category's. "
                                                   "Press R to list new profiles."}),
            },
            "hidden": {"unique_id": "UNIQUE_ID", "extra_pnginfo": "EXTRA_PNGINFO"},
        }

    @classmethod
    def VALIDATE_INPUTS(cls, user_system_prompt=None):
        # A deleted profile must not block runs that do not use it; a run that does raises a readable error.
        return True

    @classmethod
    def IS_CHANGED(cls, pin="", overrides="", scope="", user_prompt=None, user_text="", use_user_text=False,
                   user_system_prompt=NO_PROFILE, **kwargs):
        text = user_text_of(user_prompt, user_text, use_user_text)
        if text is not None:
            if _user_pin_seed(pin) is None and any(t in text for t in _WILDCARD_SYNTAX):
                return f"user:{random_seed()}"  # wildcards: a new pick every run
            try:
                llm, _name, sp_text = user_llm(get_store(), overrides, scope, user_system_prompt)
            except Exception as e:  # the run itself will raise the readable error
                return f"error:{e}"
            key = f"{text}\0{pin}\0{llm}\0{sp_text}"
            return "user:" + hashlib.sha256(key.encode("utf-8")).hexdigest()
        try:
            return get_store().fingerprint(overrides=overrides or "", pin=pin or "", scope=scope or "")
        except Exception as e:  # the run itself will raise the readable error
            return f"error:{e}"

    def run(self, pin="", overrides=None, scope="", user_prompt=None, user_text="", use_user_text=False,
            user_system_prompt=NO_PROFILE, unique_id=None, extra_pnginfo=None):
        store = get_store()
        text = user_text_of(user_prompt, user_text, use_user_text)
        if text is not None:
            llm = user_llm(store, overrides, scope, user_system_prompt)
            return user_result(text, pin, unique_id, extra_pnginfo, *llm)
        if _user_pin_seed(pin) is not None:
            pin = ""  # an image made from user text, but no user text now: normal run
        try:
            res = store.run(wildcards.expand, overrides=overrides or "", pin=pin or "", scope=scope or "",
                            resolve_system_prompt=profiles.resolve)
        except ConsoleFinished as e:
            return finished_result(store, str(e))
        p = res.plan
        used = res.used
        pin_obj = Pin(template=p.template, seed=p.seed, category=p.category, system_prompt=p.system_prompt,
                      index=p.index, repeat=p.repeat)
        try:
            # the expanded prompt goes into the image too (gallery, review), not into the run event / state
            embed.embed(extra_pnginfo, unique_id, pin_obj.to_json(), {**used, "prompt": res.prompt})
        except Exception as e:  # metadata is a bonus; never fail the run on it
            log.warning("[KDX-Wildcard-Studio] metadata not embedded: %s", e)
        summary = _summary(p)
        return {
            "ui": {"kdx_console": [{"summary": summary, "used": used}]},
            "result": (res.prompt, res.system_prompt_text if p.llm_enabled else "", p.category, p.template,
                       p.index, p.repeat_left, bool(p.llm_enabled), json.dumps(used, ensure_ascii=False)),
        }


def user_text_of(user_prompt=None, user_text="", use_user_text=False) -> str | None:
    """The user's own prompt, or None for the Studio prompt. A connected socket wins over the widget."""
    if isinstance(user_prompt, str) and user_prompt.strip():
        return user_prompt.strip()
    if use_user_text and isinstance(user_text, str) and user_text.strip():
        return user_text.strip()
    return None


def _user_pin_seed(pin) -> int | None:
    try:
        data = json.loads(pin) if isinstance(pin, str) and pin.strip() else None
    except ValueError:
        return None
    if isinstance(data, dict) and data.get("user") is True and isinstance(data.get("seed"), int):
        return data["seed"]
    return None


def user_llm(store: Store, overrides, scope, profile) -> tuple[bool, str, str]:
    """``(llm_enabled, profile name, system prompt text)`` for a run with the user's own text. Name and text
    are empty while LLM is off, so a missing profile only matters when it would really be sent."""
    cfg = store.effective(overrides or "", scope or "")[0]
    if not cfg.get("llm_enabled"):
        return False, "", ""
    name = str(profile or "").strip()
    if name == NO_PROFILE:
        name = ""
    return True, name, profiles.resolve(name)


def user_result(text: str, pin, unique_id, extra_pnginfo, llm_enabled: bool = False, system_prompt: str = "",
                system_prompt_text: str = "") -> dict:
    """Run with the user's own text: expand wildcards in it, leave the template counter alone."""
    seed = _user_pin_seed(pin)
    pinned = seed is not None
    if seed is None:
        seed = random_seed()
    prompt = wildcards.expand(text, seed) if any(t in text for t in _WILDCARD_SYNTAX) else text
    if not isinstance(prompt, str) or not prompt.strip():
        raise ConsoleError("KDX Wildcard Studio: the user prompt expanded to empty text.")
    used = {"category": USER_CATEGORY, "template": USER_TEMPLATE, "seed": seed, "user_text": text,
            "system_prompt": system_prompt, "llm_enabled": llm_enabled}
    try:
        embed.embed(extra_pnginfo, unique_id, json.dumps({"user": True, "seed": seed}), {**used, "prompt": prompt})
    except Exception as e:  # metadata is a bonus; never fail the run on it
        log.warning("[KDX-Wildcard-Studio] metadata not embedded: %s", e)
    summary = (f"✍ user prompt · seed {seed}" + (" · LLM" if llm_enabled else "")
               + (" · from image" if pinned else ""))
    return {
        "ui": {"kdx_console": [{"summary": summary, "used": used}]},
        "result": (prompt, system_prompt_text, USER_CATEGORY, USER_TEMPLATE, 1, 0, llm_enabled,
                   json.dumps(used, ensure_ascii=False)),
    }


def _blocker():
    """ComfyUI's ExecutionBlocker(None): the nodes after this one are skipped silently, no error."""
    try:
        from comfy_execution.graph_utils import ExecutionBlocker
    except ImportError:
        try:
            from comfy_execution.graph import ExecutionBlocker
        except ImportError:
            return None
    return ExecutionBlocker(None)


def finished_result(store, message: str) -> dict:
    """A stopped category is done, not broken: render nothing, say so, raise no error."""
    blocker = _blocker()
    if blocker is None:  # ComfyUI too old to block quietly: fall back to the readable error
        raise ConsoleFinished(message)
    store.notify_finished(message)
    log.info("[KDX-Wildcard-Studio] %s", message)
    return {"ui": {"kdx_console": [{"summary": "✅ " + message, "used": {}, "finished": True}]},
            "result": tuple(blocker for _ in KDX_Console.RETURN_TYPES)}


class KDX_Console_Filename:
    """Builds ``filename_prefix`` for Save Image from the run's data (template, category, seed, date, ...)."""

    CATEGORY = "KDX/Wildcard Studio"
    FUNCTION = "build"
    DESCRIPTION = ("File-name prefix for Save Image from the data of the run. Connect state_json of KDX Wildcard Studio and "
                   "use tokens such as %template%, %category%, %seed%, %index% and %date:yyyyMMdd_hhmmss%. "
                   "ComfyUI replaces %date% only when typed directly into the Save node; this node resolves it "
                   "at run time, so the template that is running can be part of the name.")
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("filename_prefix",)
    OUTPUT_TOOLTIPS = ("Connect to filename_prefix of Save Image (convert the widget to an input)",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "state_json": ("STRING", {"forceInput": True,
                                          "tooltip": "state_json of KDX Wildcard Studio (or any JSON object)"}),
                "pattern": ("STRING", {"default": "%template%_%date:yyyyMMdd_hhmmss%", "multiline": False,
                                       "tooltip": "%key% from the JSON, %a.b% nested, %date:yyyyMMdd_hhmmss%; "
                                                  "/ makes a sub-folder"}),
            },
        }

    def build(self, state_json="", pattern=""):
        try:
            return (filename.build(pattern, filename.parse_data(state_json)),)
        except filename.FilenameError as e:
            raise ConsoleError(str(e)) from None


NODE_CLASS_MAPPINGS = {"KDX_Console": KDX_Console, "KDX_Console_Filename": KDX_Console_Filename}
NODE_DISPLAY_NAME_MAPPINGS = {"KDX_Console": "🎛️ KDX • Wildcard Studio", "KDX_Console_Filename": "🏷️ KDX • Filename"}

__all__ = ["ConsoleError", "KDX_Console", "KDX_Console_Filename", "NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS",
           "get_store"]
