# REST API and events

All routes are under `/kdx_console/`. Replies are JSON with `"ok": true|false`; errors carry `"error"` and HTTP 400.

| Method | Route | Body / query | Result |
|---|---|---|---|
| GET | `state` | `?overrides=&count=&expand=1&scope=` | `{config, state, preview, warnings, wildcards, scope, channel}` (`wildcards`: folders, source, file and template counts, unknown tokens of the last run) |
| GET | `config` | | `{config}` |
| POST | `config` | `{"config": {...}}` (or the object itself) | validated `{config, warnings}`; the cursor is re-checked |
| POST | `select` | `{category, template[, mode, pin_seed]}` | puts the cursor there and selects it for manual/pin |
| POST | `skip` | `{}` | next template now (when stopped: resume) |
| POST | `reset` | `{}` | counter from the start |
| GET | `preview` | `?count=5&expand=1` | upcoming runs; `prompt` = the next prompt expanded |
| POST | `import` | `{"prune": false}` | merge templates from the wildcard folders; `prune` removes templates whose file is gone |
| GET | `templates` | | template names in the wildcard folders |
| GET | `profiles` | | KDX-LLM system-prompt profile names |
| GET | `gallery` | `?since=<epoch seconds>&limit=600&category=&template=` | `{items, more}`: images in the ComfyUI output folder that KDX Wildcard Studio made, newest first; each item has `filename`, `subfolder`, `type`, `time`, `template`, `category`, `category_name`, `seed`, `index`, `repeat`, `prompt`, `width`, `height`. Only the PNG text chunks are read, cached per file. NSFW templates are left out unless the config has `show_nsfw: true` |
| GET | `builder` | | template builder palette: `{pools, templates, snippets, starters, show_nsfw}`; `pools` has every pool with `key`, `count`, `desc` (first comment line) and the `templates` / `pools` that use it; `snippets[sex]` are ready sentences `{id, label, nodes}`; `starters[sex]` the bubbles of a new template (`sex`: `woman`, `man`, `none`) |
| GET | `builder/pool` | `?key=core/light_sky` | `{pool}`: `values` (`value`, `w`), `head` (comment lines), `count`, `templates`, `pools`, `hidden_templates` (NSFW users while the switch is off) |
| GET | `builder/template` | `?name=` | `{name, nodes, text, note, categories}`: the template as bubbles; a file with several lines comes as one group of them (`note` says so); `categories` are the keys of the categories that hold it |
| POST | `builder/parse` | `{text}` | `{nodes, text}`: a line as bubbles (line breaks become spaces) |
| POST | `builder/preview` | `{nodes, name?, count?: 3, seed?}` | `{text, warnings, samples}`: the line, rule checks (`level` `error`/`warn`, `code`, `msg`) and expansions (`seed`, `text`, `missing`) |
| POST | `builder/save` | `{name, nodes \| text, overwrite?: false, category?}` | writes `templates/<name>.txt` (`text`: a finished line instead of bubbles); an existing file gives HTTP 409 `{exists: true}` unless `overwrite`, which keeps the old file as `<name>.txt.bak`. `category` (a key) adds the template there |
| POST | `keep` | `{template \| text, seed, expected?}` | the prompt that `template` (a name) or `text` gives with `seed`, as the picks that made it: `{prompt, tree, groups, fingerprint, matches, reliable, missing}`. `tree` nodes have `id`, `kind` (`root`/`token`/`options`), `label`, `src` (the syntax), `text`, `group`, `solo`, `segs` (child nodes and `{kind: "text", pieces: [{id, lead, core, trail}]}` for plain text, in order; a piece is the words between `, . ; : ! ?`); `groups` are `{id, label, ids}`; `matches` compares `prompt` with `expected` (`null` when none was sent); `reliable` is false when the record failed its self checks. NSFW templates only with `show_nsfw` |
| POST | `keep/build` | `{template \| text, seed, locks: [ids], swaps?: {id: text}, append?, fingerprint?, count?: 3, sample_seed?}` | `{template, locks, swaps, samples, warnings}`: the template line with those parts kept, `swaps` put in place of their parts (wildcards allowed, empty removes the part) and `append` at the end; the choices around kept and replaced parts stay, everything else as written; `samples` expand it. A `fingerprint` that no longer matches (the wildcard files changed) gives HTTP 400 |
| GET | `builder/pool/edit` | `?key=core/light_sky` | `{pool: {key, desc, lines}, users, file, archive}`: `lines` are `{v, w}` values (`w` the weight as written or `null`) and `{c}` comments in file order; `users` = `{templates, pools, reach, hidden}` (`reach`: templates that read it through other pools; `hidden`: NSFW users while the switch is off); `templates/` and `packs/` are refused |
| POST | `builder/pool/check` | `{key, desc, lines, new?, seed?}` | `{warnings, users, template, samples}`: checks (`error` blocks the save) and three prompts with the edited pool from one of its templates (`template` null = the pool alone) |
| POST | `builder/pool/save` | `{key, desc, lines, new?}` | writes `<folder>/<name>.txt`: the old file becomes `<name>.txt.bak`; values that left the pool are appended to `../wildcards_archive/<folder>/<name>_archive.txt`; `new` never overwrites. `{key, created, backup, archived}` |
| POST | `builder/pool/retire` | `{key}` | the whole pool into the archive (and `.bak`), then out of the library; HTTP 409 `{in_use, users}` while a template or pool uses it |
| GET | `packs` | | `{packs, hidden, show_nsfw, licenses, default_license, templates, limits}`: installed packs (`name`, `title`, `version`, `author`, `description`, `license`, `nsfw`, `templates` as installed, `pools`, `installed_at`); NSFW packs only with `show_nsfw` (`hidden` counts the others); `templates` are the names the export form offers |
| POST | `packs/plan` | `{templates: [names], meta: {name, title?, author, version?: "1.0.0", description?, license?, nsfw?}}` | what an export would hold, without the zip: `{meta (the pack.json), files, size, errors, warnings}` |
| POST | `packs/export` | same as `packs/plan` | the pack as `application/zip` (`Content-Disposition: attachment; filename="<name>-<version>.zip"`); HTTP 400 `{errors, warnings}` when a check fails |
| POST | `packs/inspect` | the zip file as the raw body (`Content-Type: application/zip`, at most 8 MB) | `{pack, errors, warnings, templates, pools, samples, installed, size, can_install}`: the checks, every template with its `installed_as` name and whether you have one of the same name (`exists`), every pool with `status` `new` / `same` / `differs` compared with your library, 3 example prompts and the installed version of the same pack (or `null`). An unsafe zip gives HTTP 400 |
| POST | `packs/install` | the zip as the raw body; `?replace=1&category=<key>` or `&new_category=<name>` | checks again and installs (see [Packs](packs.md)); `{installed: {name, version, templates: {in_pack: installed_as}, pools, removed, replaced}, category}`. An installed pack gives HTTP 409 `{exists: true}` unless `replace=1` |
| POST | `packs/uninstall` | `{name}` | removes `packs/<name>/` and the pack's templates and takes them out of the categories: `{removed, kept}` (`kept`: templates you changed after installing; their files stay) |

**Workflow settings.** `state` and `preview` take `?scope=<JSON>`, and `skip`, `reset` and `select` take
`"scope"` in the body: `{"channel": "w_ab12cd34", "set": {"art": false, "portrait.selfie": true}}` (the value
of the Studio node's hidden `scope` widget). The reply then shows that workflow's counter (`channel`) and
preview; `config` is always the shared one.

Example:

```bash
curl -X POST http://127.0.0.1:8188/kdx_console/select \
     -H "Content-Type: application/json" -d '{"category":"art","template":"cubism"}'
```

**Bubbles.** The template builder sends and receives a template as a list of bubbles; the server writes the line:

```json
[{"t": "text", "v": "The image is "},
 {"t": "choice", "count": null, "sep": null,
  "opts": [{"w": "2", "items": [{"t": "pool", "name": "core/medium_amateur"}]},
           {"w": null, "items": [{"t": "pool", "name": "core/medium_pro"}]}]},
 {"t": "text", "v": "."}]
```

is `The image is {2::__core/medium_amateur__|__core/medium_pro__}.` A `choice` with an empty option is optional
(`{a|}`); `count` makes it a multi-pick (`"1-2"` → `{1-2$$…}`) and `sep` is the text between the picks (`null` = the
engine's `", "`). Text is escaped where it would be syntax (`\{`, `\}`, and `\|` inside a group). `{"t": "raw", "v": …}`
keeps a piece exactly as written (a brace without its partner).

## Events

Sent with ComfyUI's websocket (`PromptServer.send_sync`):

- `kdx_console.state` — the full snapshot (same shape as `GET state`) after any change
- `kdx_console.run` — `{"used": {...}}` after each successful run
- `kdx_console.finished` — `{"message": ...}` when a queued run was skipped because its category is finished (`on_end = stop`)

The panel listens to these and never polls; it fetches once when it opens and after a reconnect.
