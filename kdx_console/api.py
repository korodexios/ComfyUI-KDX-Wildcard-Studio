"""REST handlers as plain functions (``(status, dict)``), wired to aiohttp in routes.py.

GET  /kdx_console/state     snapshot {config, state, preview, warnings}; ?scope=<workflow scope JSON> gives
                            that workflow's counter and preview (skip / reset / select take "scope" too)
GET  /kdx_console/config    config
POST /kdx_console/config    full config -> validated + stored (cursor re-validated)
POST /kdx_console/select    {category, template[, mode]}  cursor (+ manual/pin target)
POST /kdx_console/reset     {}
POST /kdx_console/skip      {}
GET  /kdx_console/preview   ?overrides=&count=&expand=1   upcoming runs (+ first prompt text)
POST /kdx_console/import    {prune?: bool, restore?: bool}  merge templates from the wildcard folders (no NSFW);
                            restore also brings back templates removed in the panel
GET  /kdx_console/templates safe template names in the wildcard folders
GET  /kdx_console/profiles  KDX-LLM system-prompt profile names
GET  /kdx_console/gallery   ?since=<epoch>&limit=&category=&template=  images made by KDX Wildcard Studio, newest first
GET  /kdx_console/builder              builder palette: pools (+ users), ready sentences, starters, templates
GET  /kdx_console/builder/pool         ?key=core/light_sky   values, description and users of one pool
GET  /kdx_console/builder/template     ?name=   a template as bubbles (+ the categories it is in)
POST /kdx_console/builder/parse        {text}   a line as bubbles
POST /kdx_console/builder/preview      {nodes, name?, count?, seed?}   template line, checks, expansions
POST /kdx_console/builder/save         {name, nodes | text, overwrite?, category?}   write templates/<name>.txt
POST /kdx_console/keep                 {template | text, seed, expected?}   an image's prompt as the picks that made it
POST /kdx_console/keep/build           {template | text, seed, locks, swaps?, append?, fingerprint?, count?,
                                       sample_seed?}
                                       the template with those parts kept / replaced + live samples
GET  /kdx_console/builder/pool/edit    ?key=   a pool for the editor (description, lines, users, file)
POST /kdx_console/builder/pool/check   {key, desc, lines, new?}   checks, users, 3 prompts with the edited pool
POST /kdx_console/builder/pool/save    {key, desc, lines, new?}   write it (.bak; removed values to the archive)
POST /kdx_console/builder/pool/retire  {key}   the whole pool into the archive (409 while it is used)
GET  /kdx_console/packs                installed packs, licenses, templates for the export form
POST /kdx_console/packs/plan           {templates, meta}   what an export would hold + the checks (no zip)
POST /kdx_console/packs/export         {templates, meta}   the pack as a .zip download
POST /kdx_console/packs/inspect        zip bytes   checks, what it adds, collisions, 3 example prompts
POST /kdx_console/packs/install        zip bytes ?replace=1&category=<key>|new_category=<name>
POST /kdx_console/packs/uninstall      {name}   remove packs/<name>/ and its templates
"""

from __future__ import annotations

import json
import logging
import os

from . import builder, engine, gallery, importer, keep, packs, pools, profiles, wildcards
from . import scope as scope_mod
from .engine import ConsoleError
from .store import Store

log = logging.getLogger("KDX-Wildcard-Studio")

MAX_BODY = 512 * 1024
EVENT = "kdx_console.state"


def parse_body(body: bytes) -> dict:
    if len(body) > MAX_BODY:
        raise ConsoleError("request too large")
    try:
        data = json.loads(body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, ValueError) as e:
        raise ConsoleError(f"invalid JSON: {e}") from e
    if not isinstance(data, dict):
        raise ConsoleError("expected a JSON object")
    return data


def _scope_text(value) -> str:
    """The workflow scope as sent by the panel (JSON text or object) -> JSON text, validated."""
    if value is None or value == "":
        return ""
    sc = scope_mod.parse(value)
    return "" if sc.shared else json.dumps({"channel": sc.channel, "set": sc.set})


def snapshot(store: Store, *, overrides: str = "", count: int = 5, expand: bool = False, scope: str = "") -> dict:
    """Everything the panel shows; one source of truth in Python. ``scope``: the workflow's own
    on/off and counter (``config`` stays the shared one, ``state``/``preview`` are the workflow's)."""
    channel = Store.channel_of(scope)
    with store.lock:
        cfg = store.load_config()
        state = store.load_state()
        pv = store.preview(overrides=overrides, count=count, scope=scope)
        warnings = list(store.last_warnings)
    if expand and pv["upcoming"] and pv["upcoming"][0].get("seed") is not None:
        first = pv["upcoming"][0]
        try:
            pv["prompt"] = wildcards.expand(engine.template_token(first["template"]), int(first["seed"]))
        except Exception as e:
            pv["prompt_error"] = str(e)
    ch = state["channels"].get(channel) or {}
    try:
        wc = wildcards.info(cfg.get("wildcard_dirs"))
    except Exception as e:  # the panel must still open
        wc = {"error": str(e)}
    return {"config": cfg, "state": ch, "preview": pv, "warnings": warnings, "wildcards": wc, "scope": scope,
            "channel": channel}


def _ok(**kw) -> tuple[int, dict]:
    return 200, {"ok": True, **kw}


def _err(e: Exception, status: int = 400) -> tuple[int, dict]:
    return status, {"ok": False, "error": str(e)}


def guard(fn):
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except ConsoleError as e:
            return _err(e)
        except Exception as e:  # pragma: no cover - unexpected
            log.exception("[KDX-Wildcard-Studio] API error")
            return _err(e, 500)

    return wrapper


@guard
def get_state(store: Store, query: dict) -> tuple[int, dict]:
    count = engine._int(query.get("count"), 5, 1, 50)
    expand = str(query.get("expand", "")).lower() in ("1", "true", "yes")
    return _ok(**snapshot(store, overrides=query.get("overrides", "") or "", count=count, expand=expand,
                          scope=_scope_text(query.get("scope"))))


@guard
def get_config(store: Store) -> tuple[int, dict]:
    return _ok(config=store.load_config())


@guard
def post_config(store: Store, body: bytes) -> tuple[int, dict]:
    data = parse_body(body)
    raw = data.get("config", data)
    cfg, warns = store.save_config(raw)
    return _ok(config=cfg, warnings=warns)


@guard
def post_select(store: Store, body: bytes) -> tuple[int, dict]:
    data = parse_body(body)
    cat, tpl = str(data.get("category") or ""), engine.template_name(data.get("template") or "")
    if not cat or not tpl:
        raise ConsoleError("select needs 'category' and 'template'")
    mode = data.get("mode")
    if mode is not None and mode not in engine.MODES:
        raise ConsoleError(f"unknown mode {mode!r}")
    with store.lock:
        cfg = store.load_config()
        engine._selected(cfg, {"category": cat, "template": tpl}, "select")  # validate first
        raw = dict(cfg)
        raw["select"] = {"category": cat, "template": tpl}
        if mode:
            raw["mode"] = mode
        if "pin_seed" in data:
            raw["pin_seed"] = data["pin_seed"]
        sc = _scope_text(data.get("scope"))
        store.save_config(raw)
        store.select(cat, tpl, scope=sc)
    return _ok(**snapshot(store, scope=sc))


@guard
def post_reset(store: Store, body: bytes = b"") -> tuple[int, dict]:
    sc = _scope_text(parse_body(body).get("scope"))
    store.reset(scope=sc)
    return _ok(**snapshot(store, scope=sc))


@guard
def post_skip(store: Store, body: bytes = b"") -> tuple[int, dict]:
    sc = _scope_text(parse_body(body).get("scope"))
    store.skip(scope=sc)
    return _ok(**snapshot(store, scope=sc))


@guard
def get_preview(store: Store, query: dict) -> tuple[int, dict]:
    count = engine._int(query.get("count"), 5, 1, 50)
    expand = str(query.get("expand", "1")).lower() in ("1", "true", "yes")
    snap = snapshot(store, overrides=query.get("overrides", "") or "", count=count, expand=expand,
                    scope=_scope_text(query.get("scope")))
    return _ok(preview=snap["preview"])


@guard
def get_templates(store: Store) -> tuple[int, dict]:
    return _ok(templates=wildcards.list_templates(_show_nsfw(store)))


def _show_nsfw(store: Store) -> bool:
    """The user's "Show NSFW" setting (config show_nsfw)."""
    try:
        return bool(store.load_config().get("show_nsfw"))
    except Exception:
        return False


@guard
def post_import(store: Store, body: bytes, names: list[str] | None = None) -> tuple[int, dict]:
    data = parse_body(body)
    if names is None:
        names, existing = wildcards.list_templates(_show_nsfw(store)), wildcards.list_all_templates()
    else:
        keys = [f"__templates/{n}__" for n in names]
        names = wildcards.filter_templates(keys, include_excluded=_show_nsfw(store))
        existing = wildcards.filter_templates(keys, include_excluded=True)
    with store.lock:
        base = store.load_config()
        if data.get("restore"):  # bring back everything removed in the panel
            base = {**base, "ignored": []}
        raw, report = importer.merge(base, names, prune=bool(data.get("prune")), existing=existing)
        cfg, warns = store.save_config(raw)
    return _ok(config=cfg, report=report, warnings=warns)


def first_run_setup(store: Store) -> dict:
    """Make a fresh install work at once: starter wildcards (if there is no library) and, while the
    config has no categories, import the templates. Never raises; returns what was done."""
    done = {"starter": None, "imported": 0}
    try:
        done["starter"] = wildcards.install_starter()
        with store.lock:
            cfg = store.load_config()
            if not cfg["categories"]:
                names = wildcards.list_templates()
                if names:
                    raw, report = importer.merge(cfg, names)
                    store.save_config(raw)
                    done["imported"] = len(report["added"])
    except Exception as e:  # first-run help must never break loading
        done["error"] = str(e)
    return done


@guard
def get_profiles(store: Store) -> tuple[int, dict]:
    return _ok(profiles=profiles.names())


def output_dir() -> str | None:
    """ComfyUI's output folder (None outside ComfyUI)."""
    try:
        import folder_paths  # type: ignore

        return folder_paths.get_output_directory()
    except Exception:
        return None


@guard
def get_gallery(query: dict, root: str | None = None, store: Store | None = None) -> tuple[int, dict]:
    """Images made by KDX Wildcard Studio in the output folder, newest first (see gallery.py). NSFW templates
    (a word of the name starts with nsfw, akt or sheer) are left out unless the config says show_nsfw."""
    root = root or output_dir()
    if not root:
        raise ConsoleError("KDX Wildcard Studio: the ComfyUI output folder is not known.")
    show = _show_nsfw(store) if store is not None else False
    res = gallery.GALLERY.scan(root, **gallery.parse_query(query))
    if not show:
        res["items"] = [it for it in res["items"] if not wildcards.is_excluded(it["template"])]
    return _ok(**res, show_nsfw=show)


# ------------------------------------------------------------------------------------------- template builder


def _builder_lib():
    lib = wildcards.library()
    if not lib.data:
        raise ConsoleError("KDX Builder: no wildcard library found. Set the wildcard folders in the panel.")
    return lib


def _hide(store: Store):
    show = _show_nsfw(store)
    return (lambda name: False) if show else wildcards.is_excluded


def _wrap_builder(fn):
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except builder.BuilderError as e:
            return _err(e)
    return wrapper


@guard
@_wrap_builder
def get_builder(store: Store) -> tuple[int, dict]:
    """Palette: the pool tree (with who uses each pool), ready sentences per sex, starters and the templates."""
    lib = _builder_lib()
    hide = _hide(store)
    pools = [{**p, "templates": [t for t in p["templates"] if not hide(t)]} for p in builder.pool_index(lib)]
    return _ok(pools=pools, templates=wildcards.list_templates(_show_nsfw(store)), snippets=builder.snippets(),
               starters={s: builder.starter(s) for s in builder.SEXES}, show_nsfw=_show_nsfw(store))


@guard
@_wrap_builder
def get_builder_pool(store: Store, query: dict) -> tuple[int, dict]:
    return _ok(pool=builder.pool_detail(_builder_lib(), query.get("key", ""), _hide(store)))


@guard
@_wrap_builder
def get_builder_template(store: Store, query: dict) -> tuple[int, dict]:
    """A template as bubbles. A file with several lines (random alternatives) opens as one group of them."""
    name = builder.check_name(query.get("name", ""))
    if wildcards.is_excluded(name) and not _show_nsfw(store):
        raise ConsoleError("KDX Builder: NSFW templates are hidden (NSFW switch in the panel).")
    lib = _builder_lib()
    key = engine.TEMPLATE_PREFIX + name
    if key not in lib.data:
        raise ConsoleError(f"KDX Builder: no template {name!r}.")
    lines = builder.raw_text(lib, key).split("\n")
    text = lines[0] if len(lines) == 1 else "{" + "|".join(lines) + "}"
    note = "" if len(lines) == 1 else f"The file had {len(lines)} lines (random alternatives); they are one group now."
    cats = [c["key"] for c in store.load_config()["categories"] if engine.find_template(c, name) is not None]
    return _ok(name=name, nodes=builder.parse_line(text), text=text, note=note, categories=cats)


@guard
@_wrap_builder
def post_builder_parse(store: Store, body: bytes) -> tuple[int, dict]:
    """{text} -> {nodes}: a line typed or pasted in the text view, as bubbles."""
    text = str(parse_body(body).get("text") or "").replace("\r", "").replace("\n", " ")
    return _ok(nodes=builder.parse_line(text), text=text)


def _nodes_text(data: dict) -> str:
    if data.get("nodes") is None and isinstance(data.get("text"), str):  # a finished line (Keep parts)
        return builder.serialize(builder.parse_line(data["text"].strip()))
    return builder.serialize(builder.normalize_nodes(data.get("nodes")))


@guard
@_wrap_builder
def post_builder_preview(store: Store, body: bytes) -> tuple[int, dict]:
    """{nodes, name?, count?, seed?} -> the template line, rule checks and expansions."""
    data = parse_body(body)
    lib = _builder_lib()
    text = _nodes_text(data)
    seed = data.get("seed")
    seed = int(seed) if isinstance(seed, int) and not isinstance(seed, bool) else None
    count = engine._int(data.get("count"), 3, 1, 10)
    return _ok(text=text, warnings=builder.check(text, lib, str(data.get("name") or "")),
               samples=builder.preview(text, lib, count, seed) if text.strip() else [])


def _template_folder(lib, name: str) -> str:
    """Where templates/<name>.txt lives (its current file) or goes (the first existing wildcard folder)."""
    src = lib.sources.get(engine.TEMPLATE_PREFIX + name)
    if src:
        return os.path.dirname(os.path.dirname(src))
    dirs, _src = wildcards.resolve_dirs()
    for d in dirs:
        if os.path.isdir(d):
            return d
    raise ConsoleError("KDX Builder: no wildcard folder to save into.")


@guard
@_wrap_builder
def post_builder_save(store: Store, body: bytes) -> tuple[int, dict]:
    """{name, nodes, overwrite?, category?} -> templates/<name>.txt. An existing file is replaced only with
    overwrite (409 otherwise) and backed up as <name>.txt.bak. ``category`` (a key) adds it there in config.json."""
    data = parse_body(body)
    name = builder.check_name(data.get("name", ""))
    text = _nodes_text(data)
    lib = _builder_lib()
    folder = _template_folder(lib, name)
    try:
        res = builder.write_template(folder, name, text, overwrite=bool(data.get("overwrite")))
    except FileExistsError:
        return 409, {"ok": False, "exists": True, "error": f"templates/{name}.txt exists already."}
    added = None
    cat = str(data.get("category") or "")
    if cat:
        with store.lock:
            raw = store.load_config()
            ci = engine.find_category(raw, cat)
            if ci is None:
                raise ConsoleError(f"KDX Builder: saved, but there is no category {cat!r}.")
            tpls = raw["categories"][ci]["templates"]
            if engine.find_template(raw["categories"][ci], name) is None:
                tpls.append({"name": name, "enabled": True, "repeat": engine.DEFAULT_REPEAT})
                added = cat
            raw["ignored"] = [n for n in raw.get("ignored") or [] if n != name]
            store.save_config(raw)
    log.info("[KDX-Wildcard-Studio] builder saved templates/%s.txt%s", name, " (backup .bak)" if res["backup"] else "")
    return _ok(name=name, text=text, created=res["created"], backup=bool(res["backup"]), category=added)


# ------------------------------------------------------------------------------------------- keep parts


def _keep_input(store: Store, data: dict) -> keep.Decomposition:
    """What made the image (a template name or the expanded text) + its seed, expanded again with a record."""
    lib = _builder_lib()
    template = str(data.get("template") or "").strip()
    if template:
        name = engine.template_name(template)
        if wildcards.is_excluded(name) and not _show_nsfw(store):
            raise ConsoleError("KDX Keep parts: NSFW templates are hidden (NSFW switch in the panel).")
        text = engine.template_token(name)
    else:
        text = str(data.get("text") or "")
        if not text.strip():
            raise ConsoleError("KDX Keep parts: no template and no prompt text to take apart.")
    seed = data.get("seed")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ConsoleError("KDX Keep parts: the image has no seed, so its picks cannot be found again.")
    return keep.decompose(lib, text, seed)


def _wrap_keep(fn):
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except (keep.KeepError, builder.BuilderError) as e:
            return _err(e)
    return wrapper


@guard
@_wrap_keep
def post_keep(store: Store, body: bytes) -> tuple[int, dict]:
    """The prompt as clickable parts. ``matches`` compares it with the prompt stored in the image (None when the
    image stored none); ``reliable`` is false when the record failed its self checks."""
    data = parse_body(body)
    d = _keep_input(store, data)
    return _ok(text=d.text, seed=d.seed, prompt=d.prompt, missing=d.missing, fingerprint=d.fingerprint,
               matches=keep.compare(data.get("expected"), d.prompt), reliable=d.reliable(_builder_lib()),
               tree=d.view(), groups=d.groups())


@guard
@_wrap_keep
def post_keep_build(store: Store, body: bytes) -> tuple[int, dict]:
    """The template line with ``locks`` kept, its checks and a few expansions of it."""
    data = parse_body(body)
    d = _keep_input(store, data)
    fp = data.get("fingerprint")
    if fp and fp != d.fingerprint:
        raise ConsoleError("KDX Keep parts: the wildcard files changed since this image was taken apart. "
                           "Open it again.")
    lib = _builder_lib()
    if not d.reliable(lib):
        raise ConsoleError("KDX Keep parts: the picks of this prompt cannot be told apart reliably "
                           "(a wildcard value cuts through another one), so no part is kept.")
    locks = d.clean_locks(data.get("locks"))
    swaps = d.clean_swaps(data.get("swaps"), locks)
    text = d.render(locks, swaps, str(data.get("append") or ""))
    seed = data.get("sample_seed")
    seed = seed if isinstance(seed, int) and not isinstance(seed, bool) else None
    count = engine._int(data.get("count"), 3, 1, 10)
    changed = bool(locks or swaps or text != d.text)
    return _ok(template=text, locks=sorted(locks), swaps={str(k): v for k, v in swaps.items()},
               samples=builder.preview(text, lib, count, seed), warnings=builder.check(text, lib) if changed else [])


# ------------------------------------------------------------------------------------------- pool editor


def _wrap_pools(fn):
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except pools.PoolInUse as e:
            return 409, {"ok": False, "in_use": True, "error": str(e), "users": e.users}
        except (pools.PoolError, builder.BuilderError) as e:
            return _err(e)
    return wrapper


def _users_view(store: Store, lib, key: str) -> dict:
    """Who reads the pool, NSFW template names left out (and counted) while the NSFW switch is off."""
    if key not in lib.data:
        return {"templates": [], "pools": [], "reach": [], "hidden": 0}
    u = pools.users(lib, key)
    hide = _hide(store)
    shown = {k: [t for t in u[k] if not hide(t)] for k in ("templates", "reach")}
    hidden = len(set(u["templates"]) | set(u["reach"])) - len(set(shown["templates"]) | set(shown["reach"]))
    return {**shown, "pools": u["pools"], "hidden": hidden}


def _pool_req(data: dict) -> tuple[str, dict, bool]:
    new = bool(data.get("new"))
    return pools.check_key(data.get("key", ""), new=new), pools.normalize_model(data), new


@guard
@_wrap_pools
def get_pool_edit(store: Store, query: dict) -> tuple[int, dict]:
    """A pool as the editor shows it: description, lines (values with weights, comments), users, file paths."""
    lib = _builder_lib()
    key = pools.check_key(query.get("key", ""))
    root, path = pools.pool_path(_pack_roots(), lib, key)
    return _ok(pool=pools.read_model(path, key), users=_users_view(store, lib, key),
               file=os.path.relpath(path, root).replace(os.sep, "/"),
               archive=os.path.relpath(pools.archive_path(root, key), os.path.dirname(root)).replace(os.sep, "/"))


@guard
@_wrap_pools
def post_pool_check(store: Store, body: bytes) -> tuple[int, dict]:
    """{key, desc, lines, new?} -> rule checks, users and three prompts with the edited pool."""
    lib = _builder_lib()
    key, model, new = _pool_req(parse_body(body))
    if new:
        pools.pool_path(_pack_roots(), lib, key, new=True)  # free name?
    data_seed = parse_body(body).get("seed")
    seed = data_seed if isinstance(data_seed, int) and not isinstance(data_seed, bool) else None
    smp = pools.samples(lib, key, model, hide=_hide(store), seed=seed)
    return _ok(warnings=pools.check(lib, key, model), users=_users_view(store, lib, key), **smp)


@guard
@_wrap_pools
def post_pool_save(store: Store, body: bytes) -> tuple[int, dict]:
    """{key, desc, lines, new?} -> writes <folder>/<name>.txt (backup .bak, removed values to the archive)."""
    lib = _builder_lib()
    key, model, new = _pool_req(parse_body(body))
    res = pools.save(_pack_roots(), lib, key, model, new=new)
    log.info("[KDX-Wildcard-Studio] pool %s %s (%d value(s) archived)", key, "created" if new else "saved", res["archived"])
    return _ok(key=res["key"], created=res["created"], backup=res["backup"], archived=res["archived"])


@guard
@_wrap_pools
def post_pool_retire(store: Store, body: bytes) -> tuple[int, dict]:
    """{key} -> the whole pool moves into the archive; 409 with its users while anything reads it."""
    lib = _builder_lib()
    key = pools.check_key(parse_body(body).get("key", ""))
    try:
        res = pools.retire(_pack_roots(), lib, key)
    except pools.PoolInUse as e:
        return 409, {"ok": False, "in_use": True, "error": str(e), "users": _users_view(store, lib, key)}
    log.info("[KDX-Wildcard-Studio] pool %s retired into the archive (%d lines)", key, res["lines"])
    return _ok(key=key, lines=res["lines"])


# ------------------------------------------------------------------------------------------- packs


def _pack_roots() -> list[str]:
    dirs, _src = wildcards.resolve_dirs()
    return [os.path.abspath(d) for d in dirs if os.path.isdir(d)]


def _pack_root() -> str:
    roots = _pack_roots()
    if not roots:
        raise ConsoleError("KDX Packs: no wildcard folder to install into. Set the wildcard folders in the panel.")
    return roots[0]


def _wrap_packs(fn):
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except packs.PackExists as e:
            return 409, {"ok": False, "exists": True, "error": str(e)}
        except (packs.PackError, builder.BuilderError) as e:
            return _err(e)
    return wrapper


def _lookup(name: str) -> dict | None:
    for root in _pack_roots():
        meta = packs.read_installed(root, name)
        if meta is not None:
            return meta
    return None


def _pack_home(name: str) -> str | None:
    """The wildcard folder that holds packs/<name>/ (None when it is not installed)."""
    if not packs.PACK_NAME_RE.match(name or ""):
        return None
    return next((r for r in _pack_roots() if os.path.isdir(os.path.join(r, packs.PACKS_DIR, name))), None)


@guard
@_wrap_packs
def get_packs(store: Store) -> tuple[int, dict]:
    """Installed packs (NSFW ones only with the NSFW switch) and what the export form offers."""
    show = _show_nsfw(store)
    found = packs.list_installed(_pack_roots())
    shown = [{k: v for k, v in p.items() if k != "root"} for p in found if show or not p["nsfw"]]
    return _ok(packs=shown, hidden=len(found) - len(shown), show_nsfw=show, licenses=list(packs.LICENSES),
               default_license=packs.DEFAULT_LICENSE, templates=wildcards.list_templates(show),
               limits={"zip_mb": packs.MAX_ZIP_BYTES // (1024 * 1024), "file_kb": packs.MAX_FILE_BYTES // 1024})


def _export(store: Store, body: bytes) -> dict:
    data = parse_body(body)
    names = data.get("templates")
    if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
        raise ConsoleError("KDX Packs: templates must be a list of template names.")
    names = [engine.template_name(n) for n in names]
    if not _show_nsfw(store) and any(wildcards.is_excluded(n) for n in names):
        raise ConsoleError("KDX Packs: NSFW templates are hidden (NSFW switch in the panel).")
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    return packs.export(_builder_lib(), names, meta)


@guard
@_wrap_packs
def post_pack_plan(store: Store, body: bytes) -> tuple[int, dict]:
    """{templates, meta} -> what the zip would hold (files, size, pack.json) and the checks; no zip."""
    res = _export(store, body)
    return _ok(**{k: v for k, v in res.items() if k != "zip"})


@guard
@_wrap_packs
def post_pack_export(store: Store, body: bytes) -> tuple[int, dict]:
    """{templates, meta} -> the zip (``_zip`` bytes + ``filename``; routes.py sends it as a download)."""
    res = _export(store, body)
    if res["errors"]:
        return 400, {"ok": False, "error": "KDX Packs: the pack does not pass the checks: " + res["errors"][0]["msg"],
                     "errors": res["errors"], "warnings": res["warnings"]}
    meta = res["meta"]
    return 200, {"ok": True, "_zip": res["zip"], "filename": f"{meta['name']}-{meta['version']}.zip"}


def _inspect(store: Store, data: bytes) -> dict:
    res = packs.inspect(data, wildcards.library(), _lookup)
    if res["pack"].get("nsfw") and not _show_nsfw(store):
        res["errors"].insert(0, {"level": "error", "code": "nsfw_hidden",
                                 "msg": "This is an NSFW pack: turn on the NSFW switch in the panel to see and "
                                        "install it."})
        res["samples"] = []
        res["can_install"] = False
    return res


@guard
@_wrap_packs
def post_pack_inspect(store: Store, data: bytes) -> tuple[int, dict]:
    """zip bytes -> pack.json, checks, what it adds, what it would collide with, 3 example prompts."""
    res = _inspect(store, data)
    return _ok(**{k: v for k, v in res.items() if not k.startswith("_")})


def _unique_key(cfg: dict, name: str) -> str:
    base = engine.slug(name)
    key, i = base, 2
    while engine.find_category(cfg, key) is not None:
        key, i = f"{base}_{i}", i + 1
    return key


@guard
@_wrap_packs
def post_pack_install(store: Store, data: bytes, query: dict) -> tuple[int, dict]:
    """zip bytes + ?replace=1&category=<key>|new_category=<name> -> installed under packs/<pack>/; the templates
    go into that category (optional). The zip is checked again; nothing existing is overwritten."""
    replace = str(query.get("replace", "")).lower() in ("1", "true", "yes")
    cat, new_cat = str(query.get("category") or ""), str(query.get("new_category") or "").strip()[:80]
    if cat and engine.find_category(store.load_config(), cat) is None:
        raise ConsoleError(f"KDX Packs: there is no category {cat!r}.")
    res = _inspect(store, data)
    if res["errors"]:
        return 400, {"ok": False, "error": "KDX Packs: " + res["errors"][0]["msg"], "errors": res["errors"]}
    root = _pack_home(res["_meta"]["name"]) or _pack_root()
    done = packs.install(root, res["_meta"], res["_files"], wildcards.library(), replace=replace)
    names = list(done["templates"].values())
    target = None
    with store.lock:
        raw = store.load_config()
        gone = set(done["removed"])
        for c in raw["categories"]:
            c["templates"] = [t for t in c["templates"] if t["name"] not in gone]
        if new_cat:
            target = _unique_key(raw, new_cat)
            raw["categories"].append({"key": target, "name": new_cat, "enabled": True, "system_prompt": "",
                                      "on_end": "next", "templates": []})
        elif cat:
            target = cat
        if target:
            c = raw["categories"][engine.find_category(raw, target)]
            for n in names:
                if engine.find_template(c, n) is None:
                    c["templates"].append({"name": n, "enabled": True, "repeat": engine.DEFAULT_REPEAT})
        raw["ignored"] = [n for n in raw.get("ignored") or [] if n not in names]
        store.save_config(raw)
    log.info("[KDX-Wildcard-Studio] pack %s %s installed (%d templates, %d pools)", done["name"], done["version"],
             len(names), done["pools"])
    return _ok(installed={k: v for k, v in done.items() if k != "path"}, category=target)


@guard
@_wrap_packs
def post_pack_uninstall(store: Store, body: bytes) -> tuple[int, dict]:
    """{name} -> packs/<name>/ and its template files removed, the templates taken out of the categories."""
    name = str(parse_body(body).get("name") or "")
    root = _pack_home(name)
    if root is None:
        raise ConsoleError(f"KDX Packs: the pack {name!r} is not installed.")
    meta = packs.read_installed(root, name) or {}
    if meta.get("nsfw") is not False and not _show_nsfw(store):
        raise ConsoleError("KDX Packs: NSFW packs are hidden (NSFW switch in the panel).")
    res = packs.uninstall(root, name)
    gone = set(res["removed"])
    if gone:
        with store.lock:
            raw = store.load_config()
            for c in raw["categories"]:
                c["templates"] = [t for t in c["templates"] if t["name"] not in gone]
            store.save_config(raw)
    log.info("[KDX-Wildcard-Studio] pack %s removed (%d templates, %d kept)", name, len(gone), len(res["kept"]))
    return _ok(**res)
