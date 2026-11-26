# Changelog

## 0.7.13 - 2026-11-26

### Changed
- **The data folder is `user/kdx_wildcard_studio/`** (was `user/kdx_console/`), matching the product name. The first
  start renames the old folder (one rename: nothing is copied or deleted) and points wildcard folders in config.json
  that lay inside it at the new place. When both folders exist, the new one is used and the old one is left alone.
  A link into the old folder (for example Impact Pack's `custom_wildcards`) has to be pointed at the new one.
  The node class, REST routes and image metadata keep their names, so workflows and images work as before.
- The environment variable that overrides the folder is `KDX_WILDCARD_STUDIO_DIR` (was `KDX_CONSOLE_DIR`).

## 0.7.12 - 2026-11-26

### Added
- **Panel: fold categories.** ▾ / ▸ before a category's name folds it to one line (on/off, template count, how many
  are on, the next template when it is there); **▸ Fold all** / **▾ Unfold all** above the categories. Remembered in
  this browser only; the config and the workflow are not touched.

## 0.7.11 - 2026-11-26

### Added
- **Keep parts: keep several pieces of plain text.** A click marks a piece as kept (blue), any number of them;
  ⇄ Replace still works on the piece you clicked. **✂ Remove unmarked text** leaves out the plain text you did not
  mark, so only the wildcards, kept parts, marked text and replacements stay (spaces and commas tidied, wildcard
  syntax untouched); then add new wildcards.
- REST: `keep/build` takes `marks` and `drop_text`.

## 0.7.10 - 2026-11-26

### Added
- **Keep parts: replace plain text.** Text that is not a pick (the fixed words of the template line, or kept parts
  that are plain text now) is split into pieces at `, . ; : ! ?`; click a piece and **⇄ Replace…** puts wildcards or
  other words in its place, the punctuation around it stays. Works for prompts without any wildcards too.
- REST: `keep` returns plain text as pieces (`{kind: "text", pieces}`); `keep/build` takes piece ids (`"<node>.<seg>.<piece>"`) as `swaps` keys.

## 0.7.9 - 2026-11-26

### Added
- **Keep parts › ⇄ Replace…**: put another pool, wildcards or your own words in place of a part (search the library's
  pools or type), **↺ Original** undoes it. The choices around it are kept. **＋ Add at the end** adds text or a
  pool after the prompt.
- **Template builder › Use on node**: send the line to the Studio node as your own prompt without saving a template
  (asks before replacing text, ↶ Restore previous text).
- **Gallery › Save as template…** for images made from your own text: its prompt, wildcards included, becomes
  `templates/<name>.txt`.
- REST: `keep/build` takes `swaps` and `append`.

## 0.7.8 - 2026-11-26

### Docs
- README: which text the node uses (`user_prompt`, then `user_text` typed or wired while `use_user_text` is on,
  then the template) and the socket on the `user_text` box.

## 0.7.7 - 2026-11-26

### Fixed
- **Keep parts › Use on node with a text node wired to the `user_text` socket.** It wrote into the box, whose typed
  value ComfyUI ignores while the socket is wired, so the wired text node kept its old text. Now it writes into
  that text node and switches `use_user_text` on.

### Docs
- docs/13-your-own-prompt.md: **Which text is used** — `user_prompt`, then `user_text` (typed or wired) while
  `use_user_text` is on, then the template.

## 0.7.6 - 2026-11-26

### Changed
- **Keep parts › Use on node never overwrites your text without asking.** With a text node connected to
  `user_prompt` it offers to write into that node (it wins over `user_text`) or into `user_text`. When the chosen
  place holds other text, it shows that text and writes only after **Replace**. **↶ Restore previous text** puts the
  old text back (Ctrl+Z works too).

## 0.7.5 - 2026-11-26

### Fixed
- **NSFW switch: names with `nsfw` at the end are hidden too.** A template counted as NSFW only when its name started
  with `nsfw`, `akt` or `sheer`, so `outdoor_nsfw`, `sport_nsfw` or `atelier_nsfw` showed in the Gallery, the
  Builder, Keep parts, Add template and Import with the switch off. Now any word of the name (split at `/ _ - .`)
  that starts with one of them counts. The builder's checks use the same rule.

## 0.7.4 - 2026-11-26

### Added
- **🔒 Keep parts.** Keep the parts of an image's prompt you like (pose, clothing, place, light, style …) and let the
  rest vary. It opens from the Gallery viewer and from a Template builder sample. The prompt is shown as clickable
  wildcard picks, with quick choices for whole groups (Whole person, Face & hair, Clothing, Pose & action, Camera,
  Environment & light, Style & mood …), ⇄ Invert and live variants. Keeping a part also keeps the choice around it
  (a kept expression keeps its option, whose mood still varies); a pool value with wildcards inside can be kept
  whole or in part. The result is a template line: kept parts as fixed text, the rest as wildcards. **Use on node**
  writes it into `user_text` and switches `use_user_text` on; **Save as template…** writes `templates/<name>.txt`
  (optionally into a category); **Open in Builder** loads it there. Works for your own prompts with wildcards too.
  See docs/16-keep-parts.md.
- The window runs the image's template and seed again and compares the result with the prompt stored in the
  image. When a wildcard file has changed, it says so and keeps nothing unless you choose to work with today's
  picks.
- REST: `POST /kdx_console/keep`, `POST /kdx_console/keep/build`; `builder/save` also takes a finished `text`.
  Gallery items carry `user_text` and `llm_enabled`.

### Changed
- The wildcard engine can record which pick made which part of a prompt (`Library.expand(..., trace=True)`). The
  picks, their order and the text are exactly the same as without the record. A test checks this for every
  bundled template.

## 0.7.3 - 2026-11-26

### Added
- **Your own prompt can go through the LLM.** New widget `user_system_prompt` on the node picks the KDX-LLM system
  prompt for `user_text` / `user_prompt`.
- **LLM button on the node body**, the same switch as the LLM pill in the panel.

### Changed
- With LLM on, your own prompt now sets `llm_enabled` = true (before it was always false), so KDX-LLM Chat rewrites
  it. Turn LLM off to use your text as it is. Saved workflows load unchanged.

## 0.7.2 - 2026-11-26

### Added
- Example workflow **5 Z-Image Turbo with LLM and Resolution**: KDX Wildcard Studio → KDX LLM Chat (off with the LLM
  pill) → KDX Prompt Extractor → KDX AutoRes (Z-Image profile) → built-in loaders, sampler and Save Image, file names
  from KDX Filename. No other custom nodes. A muted text node on `user_prompt` shows the own-prompt switch; the
  loaders carry the official Z-Image Turbo download links, so ComfyUI offers to fetch missing models.

## 0.7.1 - 2026-11-26

### Changed
- **New name: KDX Wildcard Studio** (was KDX Console), so the name says what the pack is. Repository
  `ComfyUI-KDX-Wildcard-Studio`, registry id `comfyui-kdx-wildcard-studio`, node `🎛️ KDX • Wildcard Studio` in the
  **KDX/Wildcard Studio** menu, panel, docs and example workflows. The `use_user_text` switch reads "user text" /
  "templates".
- Nothing to rebuild: the node class (`KDX_Console`), the REST routes (`/kdx_console/…`) and your data folder
  (`user/kdx_console/`) keep their names, so saved workflows, images and settings work as before.

## 0.7.0 - 2026-11-26

First release candidate for publishing.

### Changed
- Package description lists what the pack does today (gallery, template builder, pool editor, packs, own prompt).
- Template builder: the name example is `portrait_woman`.

### Added
- GitHub Actions: `CI` runs the tests on Python 3.10–3.12 for every push; `Publish to Comfy Registry` publishes the
  node when a GitHub release is published (needs the `REGISTRY_ACCESS_TOKEN` secret).

## 0.6.22 - 2026-11-26

### Changed
- **Packs: the default license is now CC0-1.0** (anyone may use a shared pack for anything, no credit needed). CC-BY-4.0,
  CC-BY-SA-4.0 and MIT stay in the list for authors who want credit.

## 0.6.21 - 2026-11-25

### Fixed
- New pool: the folder field looked like a list with only one entry. It was a text field with suggestions, filled
  with the first folder (`activity`), so the browser offered only folders matching that text. It is now a drop-down
  with every folder of the library and **＋ New folder…** at the end, which opens a field for the new name (`auto`, or
  `auto/motor` for a subfolder) with the allowed characters. Nothing is picked for you: the window starts at "choose a
  folder…", or at the folder you opened it from: hover a folder in the pool list and press its ＋ (the ＋ New pool
  button above the list uses the folder of the pool you are looking at). A line under the fields shows the token that
  will be created (`__auto/motor/rpm_sound__`) or what is still missing.

### Changed
- The example library installed on first start (`starter_wildcards/`) is now a trimmed, safe-for-work copy of the
  author's own library: 16 templates (people: portrait, street, everyday, outdoor and work, each `_woman` / `_man`;
  places: landscape, architecture; things: still life, food, animal, vehicle) and 116 pools of at most 24 values, adults
  only, with every shot ending in its aspect ratio. It also holds the pools of the builder's ready sentences
  (`pose/neutral`, `pose/studio_scene`, `person/expression_soft`), so **New… › woman** passes the checks on a fresh
  install. Existing libraries are never touched.

### Docs
- User guide with screenshots: glossary, panel, Gallery, Template builder, pool editor, your own prompt, Packs and a
  step-by-step "own theme from scratch" example (`docs/08`–`docs/15`, images in `docs/images/`). The screenshots
  come from a fresh install with the example library (gallery images rendered from its templates with Z-Image Turbo).

## 0.6.20 - 2026-11-25

### Added
- **Pool editor** in the Template builder (phase 2): create and edit the wildcard pools themselves.
  - ✎ next to every pool in the palette opens it: its description (the comment lines at the top of the file) and the
    list of values. Change a value's text or weight, drag values by ⠿ to reorder them, ＋ value (Enter in a value adds
    the next one below), ✕ retires a value. Comments between values stay where they are.
  - **＋ New pool** above the pool list: pick a folder (or type a new one) and a name (`a-z`, `0-9`, `_`), add a
    description and values. An existing pool is never overwritten.
  - Beside the list: who uses the pool (templates and pools, also through short and glob tokens, and the templates it
    reaches through other pools; NSFW names only while the NSFW switch is on), the checks, and three prompts made with
    the edited pool from one of its templates (⟳ for new ones).
  - Checks: an empty or blank value, a broken weight or a second weight, an unbalanced `{ }`, an unknown or
    self-pointing token and words or ages that put a minor in the picture block the save (the same list as Packs).
    A full stop at the end (except `*scene*` pools), double spaces, spaces at the ends, duplicates, short or glob
    tokens, and clothing in a pool that an NSFW template reads (sheer templates excepted) are warnings.
  - **Nothing is deleted.** Every save keeps the old file as `<pool>.txt.bak` and writes atomically. A value that leaves
    the pool (retired, or rewritten into new wording) is appended with the date to
    `wildcards_archive/<folder>/<pool>_archive.txt` next to the library folder, where no engine loads it.
    **Retire pool** moves a whole pool there, and only while no template or pool uses it; otherwise it shows who does.
  - Never `templates/` (the builder writes those) or `packs/` (installed packs keep their checksums), and never a path
    outside the wildcard folder.
  - After a save the palette, the pool values and the preview reload.
- Routes `GET builder/pool/edit`, `POST builder/pool/check`, `POST builder/pool/save`, `POST builder/pool/retire`.

### Changed
- "Used by" counts short and glob tokens too (`__light__`, `__core/glob*__`), not only full ones. The palette marks
  the number of templates as `N tpl`.

## 0.6.19 - 2026-11-25

### Added
- **Your own prompt on the node**, outside the templates:
  - `user_prompt` input: connect any text node. Connected and not empty, its text is the `prompt` output instead of
    the template. Mute or bypass the text node (or leave it empty) and the Console prompt comes back.
  - `user_text` box and `use_user_text` switch on the node itself: type a prompt, flip the switch to "user text".
    A connected `user_prompt` wins over the box.
  - Wildcards work in your text (`__core/light_sky__`, `{a|b}`), with a new pick every run.
  - The template counter does not move while your text is used, so the Console carries on where it stopped.
    `category` = `user`, `template` = `user_prompt`, `llm_enabled` = false (the text is the prompt).
  - The image records the text, the expanded prompt and the seed; dragging it back repeats the same prompt (if the
    text is gone by then, the node simply runs the Console).
  - The node body shows "✍ user text" while the switch is on.

## 0.6.18 - 2026-11-25

### Added
- **📦 Packs**: share templates with every pool they use as one `.zip`, and install packs from others. A new window
  from the panel with three tabs:
  - **Export**: pick templates, name the pack, author, version, license, description; **Check** and **⇩ Download
    .zip**. The pack follows every token recursively (short and glob tokens bring every file they read) and carries a
    `pack.json` with the file list and md5 sums. NSFW is set by itself for NSFW template names.
  - **Import**: drop a `.zip`; it is checked (text only, no paths out of the zip, no links, size limits, UTF-8; then the
    library lint and 60 expansions per template: unknown tokens, weights, braces, minors and ages under 18, NSFW names
    in an SFW pack), and the preview shows what it adds, which pools you already have (same / different) and three
    example prompts. **Install** writes into `packs/<pack>/` and `templates/<pack>_<name>.txt`, never over an existing
    file, and can add the templates to an existing or a new category. Installing again replaces the pack (edited
    templates are kept as `.bak`).
  - **Installed**: version, author, license, templates; **Uninstall…** removes the pack folder and its templates
    (edited ones stay) and takes them out of the categories.
  - NSFW packs follow the NSFW switch (hidden, not installable or removable while it is off).
- REST: `GET packs`, `POST packs/plan`, `packs/export` (zip download), `packs/inspect` and `packs/install` (zip as the
  raw body), `packs/uninstall`.
- `docs/packs.md`: the format, the checks, the install layout, and a plan for a community pack index on GitHub
  (SFW only there, CI with the same checks, a Browse tab in Console). Not built yet.

### Changed
- Wildcards: `packs/` is a reserved folder. Short tokens and globs (`__age__`, `__*/age__`) no longer read files
  under `packs/`; `__packs/<pack>/<name>__` applies the short-name and glob rules inside that pack only. Installing a
  pack therefore never changes what your own templates pick.

## 0.6.17 - 2026-11-25

### Fixed
- Template builder: the palette tabs (Pools, Sentences, Text & groups) disappeared after switching to a long list such
  as Sentences, so the other tabs could not be reached without closing the builder. The long list squeezed the tab bar
  to nothing. The tabs and the search / sex picker now stay fixed at the top of the palette and only the list below
  scrolls, in every tab, with any list length and in a low or narrow window. A tab you switch to starts at the top.

## 0.6.16 - 2026-11-25

### Added
- Template builder: **Save as…** next to Save. It asks for a new name, suggests a free one that keeps the sex last
  (`portrait_woman` → `portrait_copy_woman`, then `portrait_copy2_woman` …), saves a new file and leaves the open
  template untouched. A copy goes into the same category as the original (the "Add to" category is preset when a
  template is opened). Cancelling keeps the old name.
- Once a template is open, Save reads **Save (replace)** and Save as… is the highlighted button; renaming in the Name
  field switches back to a plain Save. `GET builder/template` returns `categories` (the categories holding it).

## 0.6.15 - 2026-11-25

### Changed
- **The Template builder is a canvas of bubbles** (it was a fixed form of blocks). The template reads left to right as a
  row of bubbles: text bubbles (type any words straight into the template, no pool needed), pool bubbles
  (`__folder/file__`) and group boxes: ⑂ one of (`{a|b}`, a weight per option), ◐ sometimes (`{a|}`) and ⁂ pick several
  (`{1-2$$ $$a|b}`). Groups have option lanes that take bubbles too, so groups can be nested. Drag bubbles from the
  palette into the template or into an option, drag them around to reorder, or use ＋ / ← → / Del. Undo and redo
  (Ctrl+Z / Ctrl+Y), groups fold, and a Text view edits or pastes the raw line.
- **Opening a template takes it apart into bubbles**, whoever wrote it: text, pools, groups with weights, optional and
  multi-pick groups. Only a brace without its partner stays a small text-as-written bubble. Every line of the
  bundled and of a 5,800-line real library comes back unchanged. A file with several lines (random alternatives)
  opens as one group of them and is saved as one line.
- The palette has three tabs: **Pools** (folder tree, search, values on click), **Sentences** (every block of 0.6.14 as
  a ready sentence for a woman, a man or no person, with the library's default pools and rules: expression and mood
  picked together, scene bundles) and **Text & groups**.
- Checks and the live preview (3 random images, ⟳ Again) stay; the sex check now compares the name (`_woman` / `_man`)
  with the pronouns of the text.
- REST: `GET builder` returns `snippets` and `starters` instead of the block catalogue; `builder/template` returns
  `nodes`; new `POST builder/parse`; `builder/preview` and `builder/save` take `nodes` (the block `spec` is gone).

### Next
- More ready sentences (composition, gaze only, two people) and a place-with-its-light pair.

## 0.6.14 - 2026-11-25

### Added
- **🧱 Template builder** in the panel (next to 🖼️ Gallery): build a wildcard template by clicking instead of writing
  syntax. A template is a fixed list of blocks in a fixed order: medium, person (age, ethnicity), expression + mood
  (picked together: positive / neutral / negative each with its mood, or `person/expression_soft`), hair + face
  details, clothing, pose or scene bundle (`pose/*_scene`, which then also gives place and shot, and for
  `pose/lying_scene` the light), place, light, shot + camera angle, realism, palette. Every block can be switched off
  or made "sometimes" (`{…|}`), and every slot takes one or more pools with weights (`{3::__a__|__b__}`). The text
  around the slots is fixed per block and sex (woman / man / no person), so the result follows the library's rules.
- Pool browser: folder tree with search, values and description of a pool, how many values it has and which
  templates and pools use it; pools that fit the chosen slot are marked.
- Live preview: the composed line, the rule checks and 3 expansions with random seeds (⟳ Again for new ones).
- Checks shown before saving: exactly one shot with an `N:N` ratio (over 200 expansions); NSFW names (`akt`, `nsfw`,
  `sheer`) without clothing pools or clothing words; `core/light_sky` only with places that are always outdoors;
  `person/expression_*` always with a mood, and `expression_soft` for NSFW; full `__folder/file__` tokens that exist;
  one line; the name ends in `_woman` / `_man` like the chosen sex.
- Save writes `templates/<name>.txt` and can add it to a category of the panel. An existing file is replaced only after
  a confirmation, and the old one is kept as `templates/<name>.txt.bak`. Opening an existing template shows it as blocks
  when the builder could have written it, else as editable text (preview and checks still work).
- Routes `GET /kdx_console/builder`, `GET /kdx_console/builder/pool`, `GET /kdx_console/builder/template`,
  `POST /kdx_console/builder/preview`, `POST /kdx_console/builder/save`. Composing, taking apart and checking happen
  in Python (`kdx_console/builder.py`); the window only edits the block spec.

## 0.6.13 - 2026-11-25

### Added
- **NSFW switch** in the panel (config `show_nsfw`, off by default). Off: templates whose name starts with `nsfw`,
  `akt` or `sheer` stay out of “Add template”, Import and the Gallery, as before. On: they can be added and imported, and
  the Gallery shows their images. Templates already in a category keep running either way.

## 0.6.12 - 2026-11-25

### Fixed
- Gallery: ← → in the viewer step through the images in the order the grid shows them (by category and
  template). Before, they followed the time order, so the next image was not the one beside it in the grid.

## 0.6.11 - 2026-11-25

### Changed
- Gallery: the templates of a category flow side by side instead of one per row.

## 0.6.10 - 2026-11-25

### Changed
- The KDX viewer takes the light-theme class as a parameter, so the same `lightbox.mjs` serves KDX Sweep too.

## 0.6.9 - 2026-11-25

### Added
- **🖼️ Gallery** in the panel: every image KDX Console made, grouped by category and template (any number per
  template), with time, category, text and newest-N filters. A click opens the KDX viewer: the image with its template,
  seed, size, file and full prompt beside it (copy buttons), ← → to move, click for 1:1 zoom, Esc or a click beside the
  image to close, and "Pin in Console" to repeat it exactly. New route `GET /kdx_console/gallery` (reads only the PNG
  text chunks, cached per file).
- The expanded prompt is written into the image metadata (`kdx_console` chunk, key `prompt`), so the gallery shows the
  exact text. Older images fall back to the longest text input of the saved prompt.

## 0.6.8 - 2026-11-23

### Changed
- Accent colour is now the KDX blue shared by every KDX pack (dark #6f8dff, light #2f4fd1); green stays
  the colour of a finished / OK state.

## 0.6.7

- **Calm number fields in the panel.** “Images per template”, the bulk “Set” field and the pin seed are plain digit
  fields now. Before, the browser's number field changed its value on every mouse-wheel or touchpad tick while it
  had focus, so the count ran away when you scrolled. Type the number, or press ↑/↓ to step by one; Enter confirms.

## 0.6.6

- **A finished category switches auto-run off.** ComfyUI stops “Run (Instant)” and “Run (On Change)” only on an
  error, and “On Change” queues again whenever a widget changes (a randomized seed changes after every run). Since
  0.6.5 a finished category is no longer an error, so the queue kept running at full speed. Now, when a run hits a
  finished category, KDX Console sets the run mode back to plain “Run” and says so in the message.

## 0.6.5

- **A finished category is no longer an error.** When a category with `on_end = stop` has rendered its last image,
  the next queued run now renders nothing quietly (the nodes after KDX Console are skipped) and shows a
  “finished” note on the node, in the panel and as a short message, instead of the red “prompt templates failed”
  error. Press **Skip** or **Reset** to go on, as before. Very old ComfyUI versions without quiet skipping still get
  the readable error.

## 0.6.4

- **Settings per workflow:** “On/off for: This workflow” at the top of the panel gives the open workflow its own
  category/template switches and its own counter. They are saved in the workflow (Console node), so switching
  something off in one workflow no longer switches it off in the others. “Shared” (the default) works as before.
- Fix: the node body was saved as an extra value in the workflow, so ComfyUI could skip the node's saved values
  when a workflow was opened again (for example on a tab switch).

## 0.6.3

- **Fix: Import templates reported excluded templates as missing.** Templates whose names start with `nsfw`, `akt`
  or `sheer` are not added by the import, but if you added them yourself and their file exists they are no longer
  listed as missing, and “prune” no longer removes them. Only a template without a file counts as missing.

## 0.6.2

- Panel: nice in-app dialogs instead of the browser boxes (new category, rename, remove, wildcard folders — now one
  folder per line). Enter confirms, Esc cancels.
- Panel: a template whose image was made last gets a dot, the outline still marks the template of the NEXT image
  (the counter moves when a queued prompt starts, so it is ahead of the image you see finishing).

## 0.6.1

- KDX Filename: the default pattern is now `%template%_%date:yyyyMMdd_hhmmss%` (no folder).

## 0.6.0

- **New node 🏷️ KDX • Filename:** builds the Save Image `filename_prefix` from the run, e.g.
  `%template%_ZIT_%date:yyyyMMdd_hhmmss%` → `outdoor_ZIT_20261119_143005`. Connect `state_json` of the Console to it.
  Needed because ComfyUI resolves `%date%` only in the Save node itself and cannot know the running template.

- **Fix: saving a larger configuration failed with “invalid JSON”.** The REST routes read the request body with a
  single `read()`, which returns only the first TCP segment (~1.4 KB). Bodies are now read to the end.

- **Fast clicking + queue works:** a template picked with ▶ is attached to the prompt queued by the next Run (captured when Run is pressed, because ComfyUI sends prompts asynchronously)
  (`select=category.template`), so “▶ animal, Run, ▶ portrait, Run, ▶ group, Run” renders animal, portrait,
  group — one image each, counter untouched — instead of the last pick three times.

- **Manage categories in the panel — no JSON editing:** ＋ New category, ✎ rename (the key used by overrides stays),
  ▲ ▼ reorder categories, ‹ › reorder templates, ✕ remove a category or a template, and a
  “＋ Add template…” list per category (also the way to move a template to another category).
- Removing only changes the configuration; wildcard files are never touched. Removed templates are remembered in
  `ignored` so **Import** does not bring them back; “Restore all” forgets that list.

## 0.4.2

- System prompts of categories are read from KDX-LLM's prompt files (`user/kdx_llm/system_prompts/<name>.md`,
  KDX-LLM 0.10+); an old `system_prompts.json` is still read for names without a file.

## 0.4.1

- Panel: clicking a number field (images per template, bulk or single) selects its content, so typing
  replaces the number instead of appending to it ("2" + "5" no longer becomes 25).

## 0.4.0

- **Works right after installation:** on first start an example wildcard library (`starter_wildcards/`:
  people, places, things — 5 templates) is copied to `user/kdx_console/wildcards/` and imported. Only when no
  library exists; an existing one is never touched.
- The `passthrough` output is removed again: connect **`llm_enabled`** to the `llm_enabled` input of KDX-LLM
  Chat (0.9.0+). Same meaning on both sides — `True` = LLM on. Outputs are back to the 0.1.0 set.
- Panel: the small ▸ next to each template is now a real button — **▶ Start** (sequential: continue from
  here) or **▶ Use** (manual / pin: generate only this template); the chosen one shows **✓ Selected**.
- Panel: **Images per template** for all categories at once or for one category (Set / Enter writes the
  `repeat` of every template there; shows the common value, or – when they differ).
- Fix: after an update the browser kept the old panel (ComfyUI sends no cache header for `.mjs`). Module
  imports now carry `?v=<version>`, checked by a test.
- New example workflow **4 all KDX nodes**: Console → LLM Chat → Prompt Extractor → AutoRes → image.

## 0.3.0

- **Own wildcard engine** (`kdx_console/wildcard_engine.py`, MIT): `__wildcards__` (exact, short-name pools,
  globs), `{a|b}` options, `w::` weights in files and options, multi-select `{n$$…}` / `{n-m$$sep$$…}`,
  nesting, escapes, `#` comments. KDX Console no longer imports or calls the Impact Pack.
- Wildcard folders: panel **Wildcards › Folders…** (`wildcard_dirs` in config.json), env
  `KDX_CONSOLE_WILDCARD_DIRS`, or automatic: `user/kdx_console/wildcards/` (recommended; next to config and
  state, one folder to back up), else an existing Impact Pack library folder read as plain files.
- README: *Your data and backups*.
- Files are re-read automatically when they change; no refresh needed.
- The panel shows the wildcard folders, file/template counts and unknown tokens of the last run.
- Checked against the live library: all 16 templates expand fully, all 92 wildcard pools match.
- Docs: `docs/07-wildcards.md`.

## 0.2.0

- New last output `passthrough` (BOOLEAN): `True` while the LLM is off. Connect it to the `passthrough` input of
  KDX-LLM Chat (0.8.0+) to switch the LLM off without a Switch node. Existing outputs keep their positions.
- Example workflow 3 uses it instead of the If/Else Switch.

## 0.1.0

First release.

- `KDX_Console` node: outputs `prompt`, `system_prompt`, `category`, `template`, `index`, `repeat_left`,
  `llm_enabled`, `state_json`; inputs `pin` (hidden) and `overrides` (STRING socket).
- Server-side counter with categories, per-template `repeat`, per-category `on_end` (next / loop / stop),
  disabled items skipped, safe config edits during a run.
- Modes: sequential, manual, pin.
- `overrides` grammar for per-run remote control (works through Set/Get nodes).
- Persistent `config.json` / `state.json` with atomic writes, locking and `.bak` recovery.
- Impact Pack bridge; template import from folders (NSFW names excluded).
- Reproducible images: the used state and a pin are embedded in the image metadata.
- REST API `/kdx_console/*` and websocket events.
- Three example workflows (preview without a model, text to image, overrides + LLM switch).
- Side panel and node body with pill toggles, preview and a green accent; light and dark palettes.
