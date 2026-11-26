"""Write the used state into the image metadata (hidden ``EXTRA_PNGINFO``).

Measured on ComfyUI 0.45.0: the dict is shared by every node of the prompt,
so SaveImage downstream writes our changes into the PNG. We only touch our own node in
that per-prompt copy of the workflow — never the live graph or ``node.properties``.
"""

from __future__ import annotations

NODE_TYPE = "KDX_Console"
PIN_WIDGET = "pin"
PIN_WIDGET_INDEX = 0  # position of ``pin`` in widgets_values (first widget; never reorder)
META_KEY = "kdx_console"


def _set_pin(node: dict, pin_json: str) -> bool:
    wv = node.get("widgets_values")
    if isinstance(wv, list) and len(wv) > PIN_WIDGET_INDEX:
        wv[PIN_WIDGET_INDEX] = pin_json
        return True
    if isinstance(wv, dict):
        wv[PIN_WIDGET] = pin_json
        return True
    return False


def embed(extra_pnginfo, unique_id, pin_json: str, used: dict) -> bool:
    """Store ``used`` under ``kdx_console`` and put ``pin_json`` into our node's ``pin`` widget
    in the workflow. Returns True when the workflow node was found and updated.

    Nodes inside subgraphs (unique_id ``"12:5"``) only get the ``kdx_console`` chunk: a
    subgraph definition is shared by all its instances, so pinning it would pin all of them."""
    if not isinstance(extra_pnginfo, dict):
        return False
    extra_pnginfo[META_KEY] = used
    uid = str(unique_id or "")
    if not uid or ":" in uid:
        return False
    wf = extra_pnginfo.get("workflow")
    if not isinstance(wf, dict):
        return False
    for node in wf.get("nodes") or []:
        if isinstance(node, dict) and str(node.get("id")) == uid and node.get("type") == NODE_TYPE:
            return _set_pin(node, pin_json)
    return False
