# KDX Wildcard Studio

A control centre for switching **wildcard prompt templates** in ComfyUI — one node instead of
mute groups and chains of switch nodes.

- **One node**, `🎛️ KDX • Wildcard Studio` in the **KDX/Wildcard Studio** menu.
- **Built-in wildcard engine**: expands `__wildcards__`, `{a|b}` options, weights and multi-select from plain
  `.txt` files. No other custom node is needed.
- **Categories → templates**: each category holds templates from `templates/` in your wildcard library. Every
  category and every template can be switched on or off on its own.
- **Server-side counter**: every successful run (one image) moves it. After `repeat` images the next enabled
  template follows; after the last template the category's `on_end` decides: `next`, `loop` or `stop`.
  The state survives a ComfyUI restart and works with Run, Run (instant) and Run (on change).
- **Modes**: `sequential` (default), `manual` (fixed template, new wildcard seed every run), `pin` (exact repeat).
- **Remote control**: an optional `overrides` text input (`art=off, portrait.selfie=on`), which also works through
  Set/Get nodes, plus a REST API.
- **Reproducible images**: dragging a generated image back into ComfyUI repeats the same prompt.
- **Your own prompt**: connect a text node to `user_prompt` (mute it to go back to the templates) or type
  into the node's `user_text` box and flip `use_user_text`; wildcards work there too. With the LLM switch on, your
  text goes through KDX-LLM with the system prompt picked in `user_system_prompt`.
- **LLM ready**: each category can carry a KDX-LLM system-prompt profile; the `llm_enabled` output switches
  KDX-LLM Chat off (prompt passed on unchanged) while the LLM pill is off.
- **Side panel** with pill toggles, live preview of the next runs and no polling (server events only).
- **Template builder**: drag pools, your own text and groups into a template as bubbles, with live preview and rule checks.
- No extra Python dependencies, no other custom nodes.

## Requirements

- ComfyUI with the new frontend (sidebar tabs; tested on ComfyUI 0.45.0, frontend 1.59.1)
- Nothing else to start: an example library is installed on first start (see below)
- Optional: [ComfyUI-KDX-LLM](https://github.com/korodexios/ComfyUI-KDX-LLM) for system prompts
  (0.9.0 or newer for the `llm_enabled` switch)

## Installation

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/korodexios/ComfyUI-KDX-Wildcard-Studio.git
# restart ComfyUI
```

Update: `git pull` in that folder, restart ComfyUI, then reload the browser tab.

## Wildcard library

On the first start KDX Wildcard Studio copies its example library to `ComfyUI/user/kdx_console/wildcards/` and imports
its templates, so the node works right away: 16 safe-for-work templates in three categories (people: portrait,
street, everyday, outdoor and work, each for a woman and a man; places: landscape, architecture; things: still life,
food, animal, vehicle) and the pools they use. The Template builder's ready sentences work with it too. It does this
only when no wildcard library exists yet. Replace or extend it with your own files.

Put your wildcard files in `ComfyUI/user/kdx_console/wildcards/`. Each `.txt` file is one wildcard, one
value per line; the path is its name. Templates — the full prompts KDX Wildcard Studio switches between — go in
`templates/`:

```
user/kdx_console/wildcards/
  templates/
    portrait.txt          The image is {__core/medium__}. It shows a woman in her __person/age__ ...
    art/cubism.txt        sub-folder = category "art" on import
  core/medium.txt         35mm film photo
                          2::phone snapshot          <- weight: twice as likely
  person/age.txt          early 20s
                          late 30s
```

| Syntax | Meaning |
|---|---|
| `__person/age__` | one random line of `person/age.txt` |
| `{soft\|hard} light` | one of the options |
| `{3::often\|rare}`, `2::line` | weights |
| `{1-3$$, $$__core/flaw__}` | 1–3 different lines, joined with `, ` |
| `# comment` | ignored line |

Files are re-read automatically when they change. Other folders can be set in the panel
(**Wildcards › Folders…**). Full reference: [docs/07-wildcards.md](docs/07-wildcards.md).

## Quick start

1. Open the **KDX Wildcard Studio** tab in the left sidebar and click **Import templates**.
2. Add **KDX • Wildcard Studio** to your workflow and connect `prompt` to a CLIP Text Encode
   (or to KDX-LLM Chat together with `system_prompt`).
3. Toggle categories and templates, set `repeat` per template and `on_end` per category.
4. Queue as usual. The node body shows what comes next; **Skip** and **Reset** are in the panel.

## Example workflows

In ComfyUI: **Templates → Custom nodes → ComfyUI-KDX-Wildcard-Studio** (or open the files in
[`example_workflows/`](example_workflows)):

| Workflow | Shows |
|---|---|
| **1 preview the plan (no model)** | the counter moving, run after run, without loading any model |
| **2 text to image** | the console prompt driving a normal checkpoint pipeline |
| **3 overrides and LLM switch** | per-run overrides and switching KDX-LLM Chat on/off with `llm_enabled` |
| **4 all KDX nodes** | Studio → LLM Chat → Prompt Extractor → AutoRes → image: every KDX pack in one graph |
| **5 Z-Image Turbo with LLM and Resolution** | the full graph with only built-in nodes besides KDX: Studio → optional LLM → aspect ratio → native Z-Image size → image named after the template; a muted text node shows your own prompt; the models download from the note |

## Outputs

| Output | Type | Meaning |
|---|---|---|
| `prompt` | STRING | the expanded template |
| `system_prompt` | STRING | KDX-LLM profile text of the category, or of `user_system_prompt` for your own text (empty while LLM is off) |
| `category` | STRING | category key |
| `template` | STRING | template name |
| `index` | INT | image number within the template's `repeat` (from 1) |
| `repeat_left` | INT | images left for this template |
| `llm_enabled` | BOOLEAN | LLM switch from the node, panel or `overrides` — connect to KDX-LLM Chat's `llm_enabled` |
| `state_json` | STRING | the state used for this run, as JSON |

### Your own prompt instead of a template

- Connect a text node (a String / Text node) to the `user_prompt` input. While it sends text, that text is the
  `prompt`; **mute or bypass** the text node, or leave it empty, and the template prompt comes back. No switch needed.
- Or type into the node's `user_text` box and turn `use_user_text` on ("user text"); off = templates again.
  The newer frontend also shows a socket on the box: a text node wired there replaces what is typed, and the
  switch still has to be on.
- Which text wins: **1.** a text on `user_prompt`; **2.** `user_text` (typed or wired) while `use_user_text` is on;
  **3.** the template. Details: [Your own prompt on the node](docs/13-your-own-prompt.md).
- Wildcards work in your text: `a portrait, __core/light_sky__, {red|blue} dress`.
- The template counter waits meanwhile. Outputs: `category` = `user`, `template` = `user_prompt` (handy in
  KDX Filename and the Gallery). Dragging such an image back repeats its prompt.
- The **LLM** button on the node (the same switch as in the panel) sends your text through KDX-LLM Chat too: pick
  its instructions in `user_system_prompt`. Off = your text is the final prompt.

### Switching the LLM on and off

Connect `prompt` → Chat `prompt`, `system_prompt` → Chat `system_prompt` and `llm_enabled` → Chat `llm_enabled`,
then use the Chat's `response` as the final prompt. With the LLM pill off (or `llm=off` in `overrides`) Chat makes
no LLM call and `response` is the console prompt unchanged; with it on, Chat rewrites the prompt. No Switch node
needed. The same `llm_enabled` wire can drive other switches too.

### Naming the image files: KDX Filename

To see which template made which image, and when, add **🏷️ KDX • Filename**: connect `state_json` of the Studio
to it and its `filename_prefix` output to the Save Image node's `filename_prefix` (right-click the widget →
convert to input, or drag the wire onto it).

| Pattern | Result |
|---|---|
| `%template%_%date:yyyyMMdd_hhmmss%` (default) | `outdoor_20261119_143005` |
| `%template%_ZIT_%date:yyyyMMdd_hhmmss%` | `outdoor_ZIT_20261119_143005` |
| `%category%/%template%_%seed%` | `fashion/outdoor_901421304` (sub-folder `fashion`) |

Tokens: any key of the JSON (`%template%`, `%category%`, `%seed%`, `%index%`, `%repeat%`, `%mode%`, …),
`%a.b%` for nested values and `%date:format%` with ComfyUI's letters (`yyyy yy MM dd hh mm ss`).
Why a node: ComfyUI fills `%date%` only when it is typed straight into the Save node, and it cannot know the
template that is running; a prefix coming over a wire is never touched. ComfyUI still adds its own counter
(`_00001_`) after the prefix.

## Gallery

**🖼️ Gallery** in the panel opens every image KDX Wildcard Studio made, grouped by category and template, any number of
images per template (newest first). Filter by time (last hour … everything, or "since" a date and time), category,
template or prompt text, and keep only the newest N per template. A click on an image opens the viewer: large image
with what made it next to it (template, category, seed, image number, size, file, the full prompt with a copy button),
← → to move, a click on the image for 1:1 zoom, I to hide the details, Esc or a click beside the image to close.
"Pin in Studio" switches the panel to pin mode with that template and seed to repeat the image exactly.
"🔒 Keep parts" takes the prompt apart into its wildcard picks: keep the pose, the clothes, the place or the light, and
the rest (face, hair, expression …) keeps varying; any part can also be replaced by other pools or words. The result goes onto the node, into a new template or into the
builder; see [Keep parts](docs/16-keep-parts.md).
Images of NSFW templates (a word of the name starts with `nsfw`, `akt` or `sheer`: `nsfw_detail`, `outdoor_nsfw`) appear only while the panel's **NSFW** switch
is on; the same switch lets you add and import those templates.

The gallery reads only the text chunks of the PNG files in the ComfyUI output folder (never the pixels) and needs no
extra file: images saved after a KDX Wildcard Studio run carry their template and seed, and since 0.6.9 the expanded prompt.

## Template builder

**🧱 Builder** in the panel opens a canvas where you put a template together from bubbles, without writing wildcard
syntax. The template reads left to right like the sentence it makes:

- **Text bubbles**: click and type any words; they go into the template as they are (no pool needed). Spaces at the ends
  count. Drag a text bubble by its ⠿ grip.
- **Pool bubbles** (`folder/file`): one random value of that pool per image. Click one to see its values and which
  templates use it.
- **Group boxes**: ⑂ *one of* picks one option per image (`{a|b}`), the number in front of an option is its weight;
  ◐ *sometimes* has an empty option, so the content shows in about half the images (`{a|}`); ⁂ *pick several* picks
  a number of different options and joins them (`{1-2$$ $$a|b|c}`). Every option is a lane that takes bubbles,
  groups included. ▾ folds a group.

The **palette** on the left has three tabs: **Pools** (the folders of your library, with search), **Sentences** (ready
sentences for a woman, a man or no person with the library's default pools: medium, person, expression + mood picked
together, hair and face, clothing, pose or scene bundle, place, light, shot, realism, palette) and **Text & groups**.
Drag anything into the template or into a group's option, or press ＋ to add it after the selected bubble. Drag bubbles
to reorder them. With a bubble selected: ← → move it, ◐ / ⑂ wrap it in a group, ⧉ duplicates, Del removes.
Ctrl+Z / Ctrl+Y undo and redo. **Text** shows the line as text to edit or paste; **Apply** turns it back into bubbles.

On the right: the rule checks and three random images (**⟳ Again** for new seeds). The checks warn before saving:
exactly one shot with an aspect ratio `N:N`, no clothing in NSFW templates, sky light only with outdoor places,
expressions always with a mood, full `__folder/file__` tokens that exist, one line, and a name (`_woman` / `_man`)
that matches the pronouns. **Save** writes `templates/<name>.txt` in the wildcard folder and can add it to a category.
**Save as…** saves a copy under a new name (suggested: `<name>_copy_woman` …) in the same category and leaves the
open template as it is; after opening a template, Save reads **Save (replace)**.
An existing file is replaced only after you confirm, and the old one is kept as `<name>.txt.bak`. **Open…** loads any
existing template as bubbles; a file with several lines (random alternatives) opens as one group of them.

### Editing pools

**✎** next to a pool in the palette opens the pool editor: the description at the top of the file and every value with
its weight. Type to change a value, set its weight, drag ⠿ to reorder, ＋ value (or Enter) to add one and ✕ to retire
one. **＋ New pool** above the pool list (or the ＋ next to a folder) creates a pool in a folder you pick from the list, or
in a new one (＋ New folder…; names: `a-z`, `0-9`, `_`, folders also `-` and `/` for a subfolder; an existing
pool is never overwritten). Beside the list you see which templates and pools use it, the checks and three prompts made
with your edit. Words or ages that describe a minor, broken weights, unbalanced braces and unknown tokens block the
save; a full stop at the end, double spaces, duplicates and clothing in a pool an NSFW template uses are warnings.

Nothing is ever deleted: each save keeps the old file as `<pool>.txt.bak`, and a value you retire or rewrite is
appended, with the date, to `wildcards_archive/<folder>/<pool>_archive.txt` next to your wildcard folder (outside the
library, so it is never picked). **Retire pool** moves a whole pool there, and only when nothing uses it. Templates
(`templates/`) and installed packs (`packs/`) are not edited here.

## Packs: share templates

**📦 Packs** in the panel shares templates with other people as one `.zip` and installs packs you get from them.

- **Export**: tick templates, give the pack a name, your nickname and a license (default CC0-1.0, or CC-BY-4.0 for credit),
  **Check**, then **⇩ Download .zip**. The pack carries every pool the templates use, followed through the values
  (a pool whose values use other pools brings those too), plus a `pack.json` with the file list and md5 sums.
- **Import**: drop a pack `.zip`. Before anything is written you see the checks, what it adds, which of its pools
  you already have (same or different values) and three example prompts. **Install** puts it into its own folder
  `packs/<pack>/` of your wildcard library and its templates as `templates/<pack>_<name>.txt`, and can add them to a
  category (an existing one or a new one). Your own pools and templates are never overwritten: the pack's tokens
  point at its own copies.
- **Installed**: every pack with its version, author and license; **Uninstall…** removes its folder and its
  templates after you confirm (a template you edited after installing is kept).

A pack is text only. Import accepts only `.txt` files and `pack.json`, no paths outside the zip, no links, at most
8 MB (1 MB per file), UTF-8. Then the library rules are checked: one weight per line, balanced `{ }`, every token
found in the pack, adults only (words that put a minor in the picture and ages under 18 are refused), no NSFW
template in a pack that says `nsfw: false`. NSFW packs follow the NSFW switch. Details: [Packs](docs/packs.md).

## Your data and backups

Everything KDX Wildcard Studio keeps is in one folder, `<ComfyUI>/user/kdx_console/` (ComfyUI's user directory,
the same on Windows, Linux and the portable build):

```
user/kdx_console/
  config.json     categories, templates, repeat, on_end, mode, LLM switch, wildcard folders
  state.json      the counter (where the sequence is, run count, next seed)
  wildcards/      your wildcard library: templates/*.txt and the files they use
```

To back up or move your setup, copy this folder (it is also included when you back up ComfyUI's `user`
folder). The node pack itself holds no data, so updating or reinstalling it loses nothing.

## User guide (with screenshots)

- [Glossary](docs/08-glossary.md) — pool, folder, template, category, pack: what is what
- [The panel](docs/09-panel.md) — categories, templates, LLM and NSFW pills, New category, Import
- [Gallery and viewer](docs/10-gallery.md) — filters, details, Pin in Studio
- [Template builder](docs/11-template-builder.md) — bubbles, groups, checks, Save / Save as…
- [Keep parts](docs/16-keep-parts.md) — keep what you like in an image, let the rest vary
- [Pool editor](docs/12-pool-editor.md) — new pools and folders, values and weights, archive and .bak
- [Your own prompt on the node](docs/13-your-own-prompt.md) — `user_prompt`, `user_text` / `use_user_text`, which text wins
- [Packs: share and install](docs/14-packs-guide.md) — export, import, uninstall
- [Your own theme from scratch](docs/15-tutorial-own-theme.md) — a step-by-step example (parked cars)

## Documentation

- [Quick start](docs/01-quick-start.md)
- [How it works](docs/02-how-it-works.md) — categories, counter, `on_end`, modes, files
- [Overrides](docs/03-overrides.md) — remote control grammar
- [Reproducible images](docs/04-reproducible-images.md) — the pin
- [REST API and events](docs/05-rest-api.md)
- [Development](docs/06-development.md)
- [Wildcards](docs/07-wildcards.md) — library folders and syntax
- [Packs](docs/packs.md) — the pack format, the checks, install layout, and the plan for a community pack index

## License

MIT — see [LICENSE](LICENSE).
