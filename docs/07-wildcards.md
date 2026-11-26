# Wildcards

KDX Wildcard Studio has its own wildcard engine (`kdx_console/wildcard_engine.py`, MIT). It needs no other custom
node. It reads the same kind of library the Impact Pack uses — folders of `.txt` files — and understands the
syntax those files use. Same text + same seed = same prompt.

## Where the files are

**Recommended:** `<ComfyUI>/user/kdx_wildcard_studio/wildcards/`, next to `config.json` and `state.json`. ComfyUI's
user folder is the place for user data on every system (Windows, Linux, portable), it survives updates of
the node pack, and backing up `user/kdx_wildcard_studio/` saves the whole setup (see README › *Your data and backups*).

The first of these that is set wins:

1. **Panel › Wildcards › Folders…** (saved as `wildcard_dirs` in `config.json`). Several folders are
   separated by `;`. Empty = automatic.
2. Environment variable `KDX_CONSOLE_WILDCARD_DIRS` (folders separated by `:` on Linux, `;` on Windows).
3. Automatic: `user/kdx_wildcard_studio/wildcards/` as soon as it holds a `.txt` file.
4. Automatic fallback: the folders that exist among `custom_nodes/comfyui-impact-pack/custom_wildcards`,
   `custom_nodes/comfyui-impact-pack/wildcards` and `ComfyUI/wildcards`. Only the files are read there.

### Sharing the library with Impact Pack nodes

If other workflows still use Impact Pack wildcard nodes, keep one copy of the files in
`user/kdx_wildcard_studio/wildcards/` and let the Impact Pack read it through a link:

```bash
# Linux
mv  custom_nodes/comfyui-impact-pack/custom_wildcards  user/kdx_wildcard_studio/wildcards
ln -s "$PWD/user/kdx_wildcard_studio/wildcards"  custom_nodes/comfyui-impact-pack/custom_wildcards
```

On Windows use a directory junction (no admin rights needed):
`mklink /J custom_nodes\comfyui-impact-pack\custom_wildcards user\kdx_wildcard_studio\wildcards`.

**First start:** when none of these folders has any `.txt` file, KDX Wildcard Studio copies its example library
(`starter_wildcards/` in the node pack) to `user/kdx_wildcard_studio/wildcards/` and imports its templates. An
existing library is never touched.

If a key exists in more than one folder, the first folder wins. Files are re-read automatically when one is
added, removed or changed — no refresh button. Templates are the files under `templates/`.

## Files

`person/age.txt` is the wildcard `__person/age__` (lower case; `\` → `/`; spaces → `-`). One value per line.
Empty lines and lines starting with `#` are skipped. A line may start with a weight:

```
3::warm golden light      # three times as likely as a line without weight
0.5::rare platinum bob
```

## Syntax

| Write | Result |
|---|---|
| `__person/age__` | one random line of `person/age.txt` (weights respected) |
| `__age__` | no file `age.txt` at the top: all files named `age` anywhere, plus every file in a folder `age/`, pooled |
| `__person/*__`, `__*/age__` | glob over the keys, pooled |
| `{a\|b\|c}` | one option; `{3::a\|b}` weights options |
| `{a\|{b\|c}}` | inner braces first |
| `{2$$a\|b\|c}` | 2 different options, joined with `, ` |
| `{1-3$$a\|b\|c}`, `{-3$$...}` | 1 to 3 different options |
| `{2$$ and $$a\|b\|c}` | custom separator |
| `{2-3$$, $$__core/flaw__}` | 2–3 different lines of one wildcard |
| `\{ \} \|` | literal characters |
| `<lora:name:0.8>` and any other text | unchanged |

Values may contain wildcards and options; the result is expanded again until nothing changes (at most 100
passes). Each occurrence of a token is its own pick. Lines of a template that start with `#` are dropped.

A token that matches no file stays in the prompt as written (`__nope__`), is logged, and the panel shows it
under **Wildcards** after the run. Give tokens their folder (`__person/age__`) to avoid pooling by accident.

**`packs/` is reserved for installed [packs](packs.md).** Short names and globs never reach into it: `__age__`
and `__*/age__` read only your own files, even when a pack has an `age.txt`. Inside a pack the same rules apply
within that pack only: `__packs/street/age__` pools the `age` files of the pack `street`, `__packs/street/core/*__`
globs over its `core/` folder. So installing a pack never changes what your own templates pick.

## Differences from the Impact Pack engine

Measured against the live library on 2026-11-19 (16 templates × 150 seeds, 92 wildcard pools): every token
resolves, every pool has the same values, prompt lengths match. Deliberate differences:

- The random choices differ, so a given seed gives a different (equally valid) prompt than in Impact.
- Weights also work for pooled and glob tokens (Impact leaks the `0.5::` prefix there).
- An unknown short token stays `__name__` (Impact writes `__*/name__` into the prompt).
- Globs must match the whole key; Impact matches from the start only.
- Not supported (unused in the library): YAML wildcard files and the `3#__x__` quantifier.
