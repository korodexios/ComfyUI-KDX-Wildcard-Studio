# How it works

## Model

- **Category**: name, key, enabled, `system_prompt` (KDX-LLM profile name), `on_end`, and an ordered list of templates.
- **Template**: name (`templates/<name>` in the wildcard folders), enabled, `repeat` (images per template, ≥ 1).

The order of categories and templates is the order in `config.json`. Everything is managed in the panel:

- **＋ New category**, **✎** rename (the key stays), **▲ ▼** move a category, **✕** remove it.
- **‹ ›** move a template inside its category, **✕** remove it, **＋ Add template…** adds any template that is
  not used yet (to move a template to another category: remove it, then add it there).
- Removing only edits the configuration; wildcard files are never deleted. Removed templates are listed in
  `ignored`, so **Import templates** does not bring them back. **Restore all** clears that list.
- Import appends new templates at the end (new folders become new categories).

The **category key** is derived from the name without accents (`Osoba a portrét` → `osoba_a_portret`) and is
what `overrides` uses.

## The counter (sequential mode)

The cursor `(category, template, done)` points at the **next** image.

1. A run renders the template at the cursor with a wildcard seed chosen in advance (so the preview shows
   the exact prompt).
2. Only when the template expanded successfully is the run counted (`done + 1`). A failed run never moves it.
3. When `done` reaches `repeat`, the next **enabled** template in the category follows.
4. After the last template, the category's `on_end` applies:

| on_end | next run |
|---|---|
| `next` | first enabled template of the next enabled category (wraps to the first category) |
| `loop` | first enabled template of the same category |
| `stop` | the category is finished: the next queued run renders nothing and shows a “finished” note (no error) until you press **Skip** or **Reset**; “Run (On Change)” / “Run (Instant)” is switched off |

### Disabled items and edits during a run

- A disabled template or category at the cursor is skipped: the next enabled template in the same category
  (from the start again when the category loops), otherwise the next enabled category.
- Categories without templates are skipped. If nothing is enabled, the run fails with a clear message.
- Editing the config while running is safe: items are tracked by name, so reordering is fine; a deleted item
  moves the cursor to the nearest valid position; lowering `repeat` below what was already made finishes
  the template with one more image.

## Settings per workflow

By default every workflow shares the on/off switches and the counter: switching a template off in one
workflow switches it off everywhere. At the top of the panel, **On/off for: This workflow** gives the open
workflow its own settings:

- Clicking a category or template now only changes this workflow. Items that differ from the shared settings
  have a dashed border; everything else keeps following the shared settings (also templates added later).
- The workflow gets its own counter, so two workflows no longer move each other's sequence. Skip, Reset and
  ▶ Start work on this counter.
- The settings are stored in the Studio node (hidden `scope` widget), so they are saved with the workflow:
  **save the workflow** after changing them. A copy of the workflow (Save As) shares the counter of the original.
- **Same as shared** forgets the workflow's own on/off and keeps its counter; **Shared** goes back to the shared
  settings and counter completely.
- The list of categories and templates, `repeat`, `on_end`, system prompts, mode and the LLM switch stay shared.
- `overrides` still win over both.

The panel follows the open workflow tab. A Studio node inside a subgraph always uses the shared settings.

## Modes

| Mode | Template | Wildcard seed | Counter |
|---|---|---|---|
| `sequential` | the cursor | new every run | moves |
| `manual` | the selected one (▶ Use) | new every run | stays |
| `pin` | the selected one, or the pin from an image | fixed | stays |

## When does the node run?

`IS_CHANGED` returns a fingerprint of the state (cursor, run count, next seed, config, workflow settings, overrides). It changes
after every run, so every queued prompt executes the node — no `NaN`, nothing forced downstream. In pin mode
the fingerprint only depends on the pin, so an identical pinned prompt is served from the cache.

## Files

Stored in ComfyUI's user directory (`folder_paths.get_user_directory()`), folder `kdx_wildcard_studio/` (before 0.7.13 `kdx_console/`, moved there automatically on the first start):

- `config.json` — written by the panel / REST (categories, templates, mode, LLM switch)
- `state.json` — written by the node (cursor, run count, next seed, last used state)
- `wildcards/` — your wildcard library (`templates/*.txt` and the files they use); see
  [07-wildcards.md](07-wildcards.md). Used automatically as soon as it holds a `.txt` file.

Writes are atomic and locked. A damaged file is copied to `<name>.bak` and replaced by defaults, and the panel
shows a warning. `KDX_WILDCARD_STUDIO_DIR` overrides the folder.

```json
{
  "schema_version": 1,
  "llm_enabled": false,
  "mode": "sequential",
  "select": null,
  "pin_seed": null,
  "wildcard_dirs": [],
  "ignored": [],
  "categories": [
    {"key": "portrait", "name": "Portrait", "enabled": true, "system_prompt": "", "on_end": "next",
     "templates": [{"name": "portrait", "enabled": true, "repeat": 4},
                   {"name": "selfie", "enabled": false, "repeat": 2}]}
  ]
}
```

## System prompts (KDX-LLM)

`system_prompt` of a category is the name of a KDX-LLM system prompt: a text file
`user/kdx_llm/system_prompts/<name>.md` (or `.txt`) — edit it in any text editor. (A not yet migrated
`system_prompts.json` from KDX-LLM < 0.10 is still read.) The text is sent to the `system_prompt` output only while LLM is on;
an unknown profile then stops the run with a clear message.

## NSFW

Template names with a word that starts with `nsfw`, `akt` or `sheer` (words are split at `/ _ - .`, so `nsfw_detail`, `akt_back` and `outdoor_nsfw` all count) are never listed, imported or offered.
If you add such a template to the configuration yourself, import keeps it and does not report it as missing.
