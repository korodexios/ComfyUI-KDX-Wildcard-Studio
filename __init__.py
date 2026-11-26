"""KDX-Wildcard-Studio — control centre for wildcard prompt templates in ComfyUI (own wildcard engine).

The code lives in the ``kdx_console`` package:
  * ``engine.py``    — cursor, repeat, on_end, modes, preview, fingerprint (pure)
  * ``store.py``     — config.json / state.json persistence, run transaction, events
  * ``overrides.py`` — per-run remote-control string
  * ``nodes.py``     — the ``KDX_Console`` and ``KDX_Console_Filename`` nodes
  * ``filename.py``  — file-name pattern (pure)
  * ``api.py`` / ``routes.py`` — REST ``/kdx_console/*`` + ``send_sync`` events
"""

if __package__:  # loaded by ComfyUI as a package
    from .kdx_console.nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS
    from .kdx_console.routes import register as _register_routes
else:  # imported as a plain module (e.g. by pytest from the repo root)
    from kdx_console.nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS
    from kdx_console.routes import register as _register_routes

_register_routes()

WEB_DIRECTORY = "./web"
__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
