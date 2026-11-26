# Glossary

Six words come up everywhere in KDX Wildcard Studio. Two of them are easy to mix up: a **pool** is one file, a **folder**
is a directory that holds pools.

| Word | What it is | Example | Where it lives |
|---|---|---|---|
| **Library** | All your wildcard files together | — | `ComfyUI/user/kdx_wildcard_studio/wildcards/` |
| **Folder** | A directory inside the library. It only groups pools; it is never picked from by itself | `auto/`, `person/`, `core/` | `wildcards/auto/` |
| **Pool** (wildcard file) | One `.txt` file with one value per line. Each image picks one line | `auto/car_color.txt` | `wildcards/auto/car_color.txt` |
| **Value** | One line of a pool, optionally with a weight `N::` in front | `cherry red`, `2::pearl white` | a line in the pool |
| **Token** | How a template (or another pool) names a pool: the path without `.txt`, between double underscores | `__auto/car_color__` | inside a template line |
| **Template** | One full prompt, written as one line of text with tokens and groups in it. A special pool: it lives in `templates/` | `templates/cars.txt` | `wildcards/templates/cars.txt` |
| **Category** | A group of templates in the panel, with its own on/off switch and `on_end`. Categories are settings, not files | **Cars** (key `cars`) | `user/kdx_wildcard_studio/config.json` |
| **Pack** | Templates plus every pool they need, as one `.zip` to share | `cars_demo.zip` | installed into `wildcards/packs/<pack>/` |

## How they fit together

```
user/kdx_wildcard_studio/
  config.json                 categories: "Cars" → [cars]        ← panel settings
  wildcards/                  the library
    templates/
      cars.txt                A photo of a __auto/car_color__ __auto/car_body__ parked __auto/car_place__. …
    auto/                     a folder (only groups the pools below)
      car_color.txt           cherry red          ← a pool; each line is a value
                              2::pearl white      ← weight 2: twice as likely
      car_body.txt
      car_place.txt
```

When the Studio runs the template `cars`, every token is replaced by one random value of its pool:

> A photo of a **pearl white** **compact hatchback** parked **on a wet cobblestone street**. …

## Quick answers

- **"Create a new pool" or "create a new folder"?** You always create a pool. A folder is just the first part of the
  pool's name: the pool `auto/car_color` creates the folder `auto/` if it does not exist yet. A folder without pools
  does nothing.
- **Is a template a pool?** Technically yes (a `.txt` file in the library), but the Studio treats files in
  `templates/` as whole prompts: they appear in the panel, the builder writes them, and they are one line long.
- **Is a category a folder?** No. Categories exist only in `config.json`. Import puts templates from
  `templates/<sub>/` into a category named after the sub-folder, but after that the two are independent.
- **Where do I see which templates use a pool?** In the [pool editor](12-pool-editor.md) ("Used by") and in the
  builder's pool list (click a pool).

Full syntax of values and templates: [Wildcards](07-wildcards.md).
