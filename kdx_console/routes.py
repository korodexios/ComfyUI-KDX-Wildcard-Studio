"""aiohttp wiring for api.py + server->client events. Registered only inside ComfyUI.

Events (``PromptServer.send_sync``; the panel listens, it never polls):
  * ``kdx_console.state`` — full snapshot after any config/state change
  * ``kdx_console.run``   — ``{"used": {...}}`` after each successful run
  * ``kdx_console.finished`` — ``{"message": ...}`` when a run was skipped because the category is done
"""

from __future__ import annotations

import asyncio
import logging

from . import api, packs
from .nodes import get_store

log = logging.getLogger("KDX-Wildcard-Studio")


def make_listener(send):
    """Store listener -> ``send(event, payload)``; snapshot only for state/config changes."""
    store = get_store()

    def listener(kind: str, payload: dict) -> None:
        if kind in ("state", "config"):
            send(api.EVENT, api.snapshot(store))
        elif kind == "run":
            send("kdx_console.run", payload)
        elif kind == "finished":
            send("kdx_console.finished", payload)

    return listener


def register() -> bool:
    try:
        from aiohttp import web
        from server import PromptServer
    except ImportError:  # not running inside ComfyUI (tests, tools)
        return False
    try:
        server = PromptServer.instance
        routes = server.routes
        store = get_store()
        store.listeners.append(make_listener(lambda ev, data: server.send_sync(ev, data)))

        def reply(result):
            status, data = result
            if "_zip" in data:  # a pack export: send the file itself
                name = "".join(c for c in str(data.get("filename") or "pack.zip") if c.isalnum() or c in "._-")
                return web.Response(body=data["_zip"], status=status, content_type="application/zip",
                                    headers={"Content-Disposition": f'attachment; filename="{name}"'})
            return web.json_response(data, status=status)

        async def body(request, limit: int = api.MAX_BODY) -> bytes:
            # StreamReader.read(n) returns only what has arrived so far (often one TCP segment, ~1.4 KB), which
            # cut larger configs in half ("invalid JSON"). Read to the end, stop once the limit is exceeded
            # (api.parse_body / packs.read_zip then answer "too large").
            buf = bytearray()
            async for chunk in request.content.iter_chunked(65536):
                buf += chunk
                if len(buf) > limit:
                    break
            return bytes(buf)

        @routes.get("/kdx_console/state")
        async def kdx_console_state(request):
            return reply(api.get_state(store, dict(request.query)))

        @routes.get("/kdx_console/config")
        async def kdx_console_get_config(request):
            return reply(api.get_config(store))

        @routes.post("/kdx_console/config")
        async def kdx_console_post_config(request):
            return reply(api.post_config(store, await body(request)))

        @routes.post("/kdx_console/select")
        async def kdx_console_select(request):
            return reply(api.post_select(store, await body(request)))

        @routes.post("/kdx_console/reset")
        async def kdx_console_reset(request):
            return reply(api.post_reset(store, await body(request)))

        @routes.post("/kdx_console/skip")
        async def kdx_console_skip(request):
            return reply(api.post_skip(store, await body(request)))

        @routes.get("/kdx_console/preview")
        async def kdx_console_preview(request):
            return reply(api.get_preview(store, dict(request.query)))

        @routes.get("/kdx_console/templates")
        async def kdx_console_templates(request):
            return reply(api.get_templates(store))

        @routes.post("/kdx_console/import")
        async def kdx_console_import(request):
            return reply(api.post_import(store, await body(request)))

        @routes.get("/kdx_console/profiles")
        async def kdx_console_profiles(request):
            return reply(api.get_profiles(store))

        @routes.get("/kdx_console/gallery")
        async def kdx_console_gallery(request):
            # reading many PNG headers is file I/O: keep it off the event loop
            loop = asyncio.get_running_loop()
            return reply(await loop.run_in_executor(None, api.get_gallery, dict(request.query), None, store))
        # template builder: reading the library and expanding hundreds of samples is work, keep it off the loop
        async def run(fn, *a):
            return reply(await asyncio.get_running_loop().run_in_executor(None, fn, *a))

        @routes.get("/kdx_console/builder")
        async def kdx_console_builder(request):
            return await run(api.get_builder, store)

        @routes.get("/kdx_console/builder/pool")
        async def kdx_console_builder_pool(request):
            return await run(api.get_builder_pool, store, dict(request.query))

        @routes.get("/kdx_console/builder/template")
        async def kdx_console_builder_template(request):
            return await run(api.get_builder_template, store, dict(request.query))

        @routes.post("/kdx_console/builder/parse")
        async def kdx_console_builder_parse(request):
            return await run(api.post_builder_parse, store, await body(request))

        @routes.post("/kdx_console/builder/preview")
        async def kdx_console_builder_preview(request):
            return await run(api.post_builder_preview, store, await body(request))

        @routes.post("/kdx_console/builder/save")
        async def kdx_console_builder_save(request):
            return await run(api.post_builder_save, store, await body(request))

        @routes.get("/kdx_console/builder/pool/edit")
        async def kdx_console_pool_edit(request):
            return await run(api.get_pool_edit, store, dict(request.query))

        @routes.post("/kdx_console/builder/pool/check")
        async def kdx_console_pool_check(request):
            return await run(api.post_pool_check, store, await body(request))

        @routes.post("/kdx_console/builder/pool/save")
        async def kdx_console_pool_save(request):
            return await run(api.post_pool_save, store, await body(request))

        @routes.post("/kdx_console/builder/pool/retire")
        async def kdx_console_pool_retire(request):
            return await run(api.post_pool_retire, store, await body(request))

        # wildcard packs: zips are read and checked (hundreds of expansions) off the event loop
        zip_limit = packs.MAX_ZIP_BYTES + 1

        @routes.get("/kdx_console/packs")
        async def kdx_console_packs(request):
            return await run(api.get_packs, store)

        @routes.post("/kdx_console/packs/plan")
        async def kdx_console_packs_plan(request):
            return await run(api.post_pack_plan, store, await body(request))

        @routes.post("/kdx_console/packs/export")
        async def kdx_console_packs_export(request):
            return await run(api.post_pack_export, store, await body(request))

        @routes.post("/kdx_console/packs/inspect")
        async def kdx_console_packs_inspect(request):
            return await run(api.post_pack_inspect, store, await body(request, zip_limit))

        @routes.post("/kdx_console/packs/install")
        async def kdx_console_packs_install(request):
            return await run(api.post_pack_install, store, await body(request, zip_limit), dict(request.query))

        @routes.post("/kdx_console/packs/uninstall")
        async def kdx_console_packs_uninstall(request):
            return await run(api.post_pack_uninstall, store, await body(request))
    except Exception as e:  # never break node loading because of the UI helpers
        log.warning("[KDX-Wildcard-Studio] web routes not registered: %s", e)
        return False
    done = api.first_run_setup(store)
    if done.get("starter") or done.get("imported") or done.get("error"):
        log.info("[KDX-Wildcard-Studio] first run: %s", done)
    return True
