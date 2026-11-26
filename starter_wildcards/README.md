# KDX Wildcard Studio starter wildcards

A safe-for-work example library: 16 templates and about 110 pools, a trimmed copy of the author's own library. On
first start KDX Wildcard Studio copies it to `ComfyUI/user/kdx_wildcard_studio/wildcards/` (only when no wildcard library exists yet)
and imports the templates, so the node works right after installation. Edit the copy in the user folder, not this
one; add your own files next to it. Syntax: `docs/07-wildcards.md`; the words: `docs/08-glossary.md`.

- `templates/<category>/<name>.txt`: the full prompts KDX Wildcard Studio switches between (folder = category on import)
  - `people/`: portrait, street, everyday, outdoor and work, each as `_woman` and `_man`
  - `places/`: landscape, architecture
  - `things/`: still life, food, animal, vehicle
- `core/`: medium, camera angle, light, mood, palette, places, shot (every shot value ends with its aspect ratio)
- `person/`, `man/`, `clothing/`, `pose/`, `activity/`, `company/`: people, adults only
- `animal/`, `architecture/`, `food/`, `still/`, `vehicle/`: subjects without people

The first comment line of a pool says what it holds and how the template reads it ("predicate phrases after
'her expression is'"). One concept has one owner: light only in `core/light_*`, places only in `core/place_*`, so two
slots never contradict each other. Keep it that way when you add values.
