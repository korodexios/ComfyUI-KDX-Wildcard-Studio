# Reproducible images

The counter lives on the server, so a plain workflow saved in an image would produce the *next* template, not
the one in the picture. KDX Wildcard Studio fixes this without patching the frontend:

1. During the run the node writes what it used into the image metadata (the `EXTRA_PNGINFO` that Save Image
   embeds):
   - a `kdx_console` entry with category, template, index, seed and mode,
   - in the **image's copy** of the workflow, its own hidden `pin` widget, set to
     `{"category", "template", "seed", "index", "repeat", "system_prompt"}`.
2. Drag the image back into ComfyUI: the node opens in pin mode (📌 on the node body) and renders exactly the
   same prompt. The counter does not move.
3. Click **Clear pin** on the node to return to normal mode.

The live workflow on the canvas is never changed during a run; only the copy that goes into the image is.

Nodes inside a subgraph get only the `kdx_console` metadata entry, because a subgraph definition is shared by
all its instances and pinning it would pin all of them.
