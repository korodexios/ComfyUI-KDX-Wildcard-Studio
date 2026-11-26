# Packs

A how-to with screenshots: [Packs: share and install templates](14-packs-guide.md).

A pack shares templates together with every pool they need, as one `.zip`. **📦 Packs** in the panel exports,
checks, installs and removes them. Part 1 describes what is built (0.6.18). Part 2 is a plan for a community pack
index on GitHub; none of it exists yet.

## Part 1: packs in KDX Wildcard Studio

### The zip

A pack is a small wildcard library:

```
pack.json
templates/street_woman.txt      the templates, one line each
core/light_sky.txt              every pool the templates reach
person/age_band.txt
...
```

`pack.json`:

```json
{
  "format": 1,
  "name": "street",
  "title": "Street portraits",
  "version": "1.0.0",
  "author": "nickname",
  "description": "Candid street portraits, one per sex.",
  "license": "CC0-1.0",
  "nsfw": false,
  "created": "2026-11-25",
  "templates": ["street_man", "street_woman"],
  "files": {"core/light_sky.txt": "<md5>", "templates/street_woman.txt": "<md5>"}
}
```

| Field | Rule |
|---|---|
| `format` | `1` |
| `name` | 2–32 characters, `a-z 0-9 _`, starts with a letter. It names the install folder and prefixes the templates |
| `version` | three numbers, `1.0.0` |
| `author` | required, at most 64 characters (a nickname is fine) |
| `license` | default `CC0-1.0`; `CC0-1.0`, `CC-BY-4.0`, `CC-BY-SA-4.0` or `MIT` pass without a warning |
| `nsfw` | `true` or `false`; must be `true` when a word of a template name starts with `nsfw`, `akt` or `sheer` |
| `templates` | exactly the files in `templates/` |
| `files` | every `.txt` file of the zip with the md5 of its text (`\n` line ends, one final newline) |

### Export

Tick templates, fill in the form, **Check**, **⇩ Download .zip**. Export follows every token in the templates and,
recursively, in the values of the pools they reach. A short or glob token (`__light__`, `__core/*__`) brings every
file it reads, so the pack picks exactly what your library picks. Files are copied as they are (comments and
weights kept). Templates in sub-folders (`templates/people/portrait.txt`) become flat names (`people_portrait`).
A template that uses an installed pack cannot be exported: share that pack instead. The export runs the same
checks as an import and refuses a pack with errors; the zip is deterministic (same library, same bytes).

### Import checks

Nothing in a pack is ever run; it is read as text. The zip is refused before anything else when it has:

- a file that is not `.txt` or `pack.json`, a path that is absolute, has `..`, `\`, `:` or an empty part, a
  symbolic link or any other non-regular file, an encrypted file, two files whose names differ only in case;
- more than 8 MB as a zip, a file over 1 MB, more than 16 MB unpacked, more than 2000 files (a file is never read
  past its limit, whatever its header says);
- text that is not UTF-8, or no `pack.json` at the top (one wrapping folder, `mypack/pack.json`, is accepted).

Then the library rules, the same as the library's own lint and `struct` check:

| Error (blocks the install) | Warning |
|---|---|
| `pack.json` fields above, file list, md5 | license outside the list |
| paths: lower case `a-z 0-9 _ -`, at most 6 folders deep, `templates/<name>` flat, `packs/` reserved | a template with more than one line |
| an empty pool, a line over 4000 characters, control characters, two weights on one line, unbalanced `{ }` | a duplicate value |
| a token the pack does not hold, a token into `packs/`, a short token that reaches templates | a short or glob token (`__light__`) |
| words that put a minor in the picture (`child`, `girl`, `teen`, `schoolgirl`, …) or an age under 18, in any value and in 60 expansions per template | expansions without exactly one aspect ratio `N:N`, double spaces, broken punctuation, a lower-case start |
| an NSFW template name in a pack with `nsfw: false` | the builder's hints: expression without mood, sky light indoors, name vs. pronouns |
| tokens left or weights leaking into the text after expanding | |

Packs describe adults only, from the early twenties up. The word check is a safety net, not a guarantee: read a
pack before you share it.

### Install

The preview shows the checks, the templates and the names they get, every pool and whether you have one of the same
name (same values or different), and three example prompts. Install writes into the first wildcard folder:

```
packs/street/pack.json            pack.json + an "installed" record (template names, md5, time)
packs/street/core/light_sky.txt   the pools, tokens rewritten
templates/street_woman.txt        the templates as <pack>_<name> (a name that starts with <pack>_ stays);
                                  nsfw packs: nsfw_<pack>_<name>
```

Tokens are rewritten to the pack's own namespace: `__core/light_sky__` → `__packs/street/core/light_sky__`,
`__templates/x__` → `__templates/street_x__`. A short or glob token keeps its meaning inside the pack
(`__light__` → `__packs/street/light__` pools the pack's `light` files only), and nothing outside a pack reaches
into it (see [Wildcards](07-wildcards.md)). So a pack expands exactly as it did on its own, and your library is
unchanged: an existing pool or template is never overwritten; a template name that is taken gets `_2`, `_3`, ….
The templates can go into an existing category or a new one.

Installing a pack that is installed asks to **Replace** it. Its templates keep their names; a template you edited is
saved as `<name>.txt.bak` first; templates the new version no longer has are removed (unless you edited them).

NSFW packs follow the NSFW switch: with the switch off they are not listed, cannot be installed or removed, and their
example prompts are not shown. Their templates start with `nsfw_` and are hidden like any NSFW template.

### Uninstall

**Uninstall…** (after a confirmation) deletes `packs/<pack>/` and the pack's template files and takes the templates
out of every category. A template you changed after installing is kept and listed. Nothing else is touched.

## Part 2: a community pack index (plan, not built)

Goal: people share packs through one GitHub repository; KDX Wildcard Studio gets a **Browse packs** tab that lists them and
installs one with a click, through the same checks as a manual import. Nothing here is set up or published yet.

### Repository

```
kdx-console-packs/
  packs/<github-login>/<pack>/          an unpacked pack: pack.json, templates/, pool folders
  index.json                            generated by CI on main, never edited by hand
  CONTENT_POLICY.md                     the rules below
  .github/CODEOWNERS                    maintainers review every pack
  .github/workflows/validate.yml        on pull_request
  .github/workflows/publish.yml         on push to main
  .github/ISSUE_TEMPLATE/report-pack.yml
```

A contributor adds or updates `packs/<their login>/<pack>/` in a pull request. A pack folder is exactly the zip
layout, so a reviewer reads plain text diffs.

### CI on every pull request (`validate.yml`)

- Trigger `pull_request` (never `pull_request_target`), `permissions: contents: read`, no secrets. The PR's files are
  only read as text; nothing from the PR is executed.
- Install a pinned KDX Wildcard Studio release and run its checks on every changed pack folder (a small
  `python -m kdx_console.packs validate <folder>` entry point that wraps `read`/`parse_meta`/`validate`; to be added
  with this phase). The same code as the Studio import, so CI and Studio can never disagree.
- Extra rules for the public index:
  - `nsfw` must be `false`, no template name with a word starting with `nsfw`, `akt`, `sheer`, and a word list for nudity and
    sexual content over the values and 1,000 expansions per template;
  - the minor words and ages under 18 at 1,000 expansions per template (Studio uses 60);
  - the license must be one of the four, the folder must be `packs/<PR author's login>/` (maintainers may move
    packs), the version must be higher than the one on main, at most 2 MB per pack;
  - only `.txt` and `pack.json` in the folder; the md5 in `pack.json` must match.
- The job writes a summary (errors, warnings, 3 example prompts per template) to the PR.

### Publish (`publish.yml`)

On push to main: build each pack's zip with the deterministic exporter, compute sha256, and write `index.json` and the
zips to a `dist` branch. The Studio reads `https://raw.githubusercontent.com/<owner>/kdx-console-packs/dist/index.json`.

```json
{
  "format": 1,
  "generated": "2026-12-01T10:00:00Z",
  "packs": [
    {"id": "nickname/street", "name": "street", "title": "Street portraits", "version": "1.2.0",
     "author": "nickname", "license": "CC-BY-4.0", "description": "…", "templates": ["street_man", "street_woman"],
     "pools": 23, "size": 18342, "sha256": "…",
     "zip": "https://raw.githubusercontent.com/<owner>/kdx-console-packs/dist/zips/nickname/street-1.2.0.zip",
     "source": "https://github.com/<owner>/kdx-console-packs/tree/main/packs/nickname/street",
     "updated": "2026-12-01"}
  ]
}
```

### Browse packs in Studio

- A fourth tab, **Browse**. The index URL is a setting (default: the community repository); nothing is fetched until
  the tab is opened, then at most once an hour.
- The server fetches (not the browser): only `https://` URLs on hosts allowed by the setting (by default
  `raw.githubusercontent.com`), 10 s timeout, the index capped at 2 MB and a zip at 8 MB. A zip is installed only when
  its sha256 matches the index, and then goes through the same inspect → preview → install as a manual import.
- The list shows title, author, license, templates, size, and *installed* / *update available* (version compare).
  Search and a license filter. The index never lists NSFW packs.
- New REST routes: `GET packs/index` (the cached index plus installed versions), `POST packs/fetch {id}` (download,
  verify, inspect; then the usual `packs/install`).

### Content rules (`CONTENT_POLICY.md`)

- **SFW only on GitHub.** GitHub's Acceptable Use Policies restrict sexually explicit content, so the index takes no
  nudity and no sexual content, and CI refuses `nsfw: true`. NSFW packs are shared elsewhere, on a platform whose rules
  allow mature content when it is marked (for example Civitai or Hugging Face, each under its own policy), and
  installed through **Import** (Studio keeps them behind the NSFW switch). The index does not link to them.
- **Adults only, never a minor.** People in a pack are adults from the early twenties up; no words, ages or
  descriptions that put a minor in the picture, in any context. CI checks words and ages; reviewers read the pack.
  A breach means removal and a ban of the account from the repository.
- **No real people, no impersonation.** No names or likenesses of real private persons; no prompts that imitate a
  living artist's name as a style shortcut.
- **License.** Every pack carries `CC0-1.0`, `CC-BY-4.0`, `CC-BY-SA-4.0` or `MIT`. The contributor confirms in the PR
  that they wrote the text or may share it under that license (no copied paid prompt packs).
- **Moderation.** CODEOWNERS (the maintainers) approve every PR; CI green is required, not sufficient. Anyone can
  report a pack with the issue template; a maintainer removes it from `index.json` at once (the next publish run) and
  decides afterwards. Studio shows only what the current index lists, so a removed pack disappears from Browse;
  installed copies stay with their users.

### Before this is built

Creating the repository, its workflows and the default index URL in Studio needs the maintainer's explicit go-ahead
(name, owner account, maintainers). Nothing is published from KDX Wildcard Studio automatically.
