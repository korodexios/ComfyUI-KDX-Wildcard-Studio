# Quick start

New here? The [user guide](08-glossary.md) explains every part with screenshots, and
[Your own theme from scratch](15-tutorial-own-theme.md) builds a first theme step by step.

Tip: the example workflows (**Templates → Custom nodes → ComfyUI-KDX-Wildcard-Studio**) are a ready start.

## 1. Templates

KDX Wildcard Studio expands wildcards with its own engine ([07-wildcards.md](07-wildcards.md)). Put your `.txt`
wildcard files in `ComfyUI/user/kdx_wildcard_studio/wildcards/` (other folders: panel › **Wildcards › Folders…**).
A **template** is a wildcard file under `templates/` (for example `templates/portrait.txt`), usually one full
prompt built from other wildcards:

```
The image is {__core/medium__}. It shows a woman in her {__person/age__} ...
```

Templates in sub-folders become categories on import: `templates/art/cubism.txt` lands in category `art`.
Flat files land in the category **Templates**.

## 2. Import

Open the **KDX Wildcard Studio** sidebar tab and click **Import templates**. New templates are appended; existing
settings are kept. Run it again whenever you add template files. Changed files are picked up on the next run
without any refresh.

## 3. Wire the node

```
KDX • Wildcard Studio ──prompt──────────► CLIP Text Encode ─► KSampler ─► VAE Decode ─► Save Image
              └─system_prompt──► (optional) KDX-LLM Chat  system_prompt
              └─llm_enabled────► (optional) KDX-LLM Chat  llm_enabled (off = prompt unchanged)
```

The node has no visible widgets. Everything is set in the panel (sidebar tab or the ⚙ button on the node).

## 4. Plan the run

- Click a **category pill** to switch the whole category on or off.
- Click a **template pill** to switch one template on or off.
- The number next to a template is its **repeat** (images per template).
- Many at once: **Images per template, all** (under the mode buttons) or **Images per template here** (in each
  category) + **Set** or Enter writes that number into every template there.
  Single templates can still be changed afterwards.
- The dropdown on the category is **on_end**: next category, loop the category, or stop.
- **▶ Start** next to a template continues the sequence from there; in Manual or Pin mode the button reads
  **▶ Use** and picks the only template to generate (shown as **✓ Selected**).
- **Preview** lists the next five runs; **Show prompt** expands the next prompt exactly as it will be used.

## 5. Queue

Each successful run moves the counter by one. Use Run (instant) or a batch count as usual — every queued
prompt sees the state left by the previous one.
