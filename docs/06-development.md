# Development

## Layout

```
__init__.py              ComfyUI entry (NODE_CLASS_MAPPINGS, WEB_DIRECTORY)
kdx_console/
  engine.py              cursor, repeat, on_end, modes, preview, fingerprint — pure functions
  store.py               config.json / state.json, atomic writes, run transaction, events
  overrides.py           the overrides grammar
  importer.py            templates -> categories
  wildcard_engine.py     own wildcard engine (files, __tokens__, {options}) — pure, no ComfyUI
  wildcards.py           wildcard folders (config > env > auto), template list, NSFW filter
  profiles.py            KDX-LLM system-prompt profiles (read-only)
  embed.py               image metadata / pin
  nodes.py               the KDX_Console node (V1 API)
  api.py, routes.py      REST handlers and aiohttp wiring
web/
  kdx_console.js         extension entry: sidebar tab + node hooks
  kdx_console/*.mjs      client (events), panel, node body, theme
tests/                   pytest
```

`engine.py`, `store.py`, `overrides.py` and `wildcard_engine.py` do not import ComfyUI, so the logic is tested on its own.

## Tests and lint

```bash
uv run --with pytest python -m pytest -q
uvx ruff check .
```

## Rules

- Node inputs are positional in saved workflows: never rename or reorder them; add new ones at the end.
  `pin` must stay the first widget.
- Output types are concrete (STRING/INT/BOOLEAN), never `*`.
- One frontend hook only: `app.queuePrompt` and `api.queuePrompt` are wrapped (client.mjs): the pick is taken when Run is pressed and attached to the
  queued prompt as `overrides=select=…` — it edits the API copy of the prompt, never the graph.
  Nothing is written to the live graph during a run.
- The panel reacts to server events only — no timers or polling.
- The Python engine is the single source of truth; the panel asks the server for previews.
