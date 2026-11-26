// KDX Wildcard Studio - write a prompt where the Studio node reads it (Keep parts, Template builder).
//
// The node reads, in this order: a text wired into user_prompt; user_text (typed, or wired into its socket) while
// use_user_text is on; the template. A wired input ignores the typed value, so the text goes into the wired node.
// Nothing is written without the user's click, and nothing is replaced without asking; the old values are returned
// so the caller can offer "Restore previous text" (Ctrl+Z works as well).
import { app } from "../../../scripts/app.js";
import { consoleNodes, toast } from "./client.mjs?v=0.7.11";
import { askPick } from "./dialog.mjs?v=0.7.11";

function targetNode() {
  const nodes = consoleNodes();
  if (!nodes.length) { toast("No KDX Wildcard Studio node in the open workflow."); return null; }
  const sel = Object.values(app.canvas?.selected_nodes || {}).filter((n) => nodes.includes(n));
  if (sel.length === 1) return sel[0];
  if (nodes.length === 1) return nodes[0];
  toast("Several KDX Wildcard Studio nodes: select the one to write into, then click again.");
  return null;
}

/** The node wired into the input `name`, with the string widget that holds its text (widget null: nothing to write). */
function wiredSource(node, name) {
  const slot = node.inputs?.findIndex((i) => i.name === name && i.link != null) ?? -1;
  if (slot < 0) return null;
  const src = node.getInputNode?.(slot);
  if (!src) return null;
  const strings = (src.widgets || []).filter((w) => typeof w.value === "string" && !w.hidden && w.type !== "combo");
  const widget = strings.find((w) => ["text", "value", "string", "prompt"].includes(w.name)) || strings[0] || null;
  return { node: src, widget, muted: src.mode === 2 || src.mode === 4, title: src.title || src.type };
}

function writeWidget(node, w, value) {
  w.value = value;
  w.callback?.(value);
  node.setDirtyCanvas?.(true, true);
}

function graphChanged() {
  app.graph?.change?.();
  try { app.extensionManager?.workflow?.activeWorkflow?.changeTracker?.checkState?.(); } catch (_e) { /* older frontend */ }
}

/** Write `text` for the Studio node. Resolves to an undo record `{label, items}` or null (nothing written). */
export async function useTextOnNode(text) {
  const node = text && targetNode();
  if (!node) return null;
  const ut = node.widgets?.find((x) => x.name === "user_text");
  const sw = node.widgets?.find((x) => x.name === "use_user_text");
  if (!ut || !sw) { toast("This node has no user_text / use_user_text widgets."); return null; }
  const up = wiredSource(node, "user_prompt");
  const tw = wiredSource(node, "user_text");
  const wins = up && !up.muted ? "user_prompt is connected and wins over user_text: mute or bypass its source to use this." : "";
  const options = [];
  if (up?.widget) {
    options.push({ id: "prompt", label: `Text node "${up.title}" (#${up.node.id}) on user_prompt`, current: up.widget.value, where: `"${up.title}"`,
      note: up.muted ? "It is muted or bypassed, so the Studio does not read it now." : "", items: [[up.node, up.widget, text]] });
  }
  if (tw?.widget) {
    options.push({ id: "text_src", label: `Text node "${tw.title}" (#${tw.node.id}) on user_text, use_user_text on`, current: tw.widget.value,
      where: `"${tw.title}"`, note: wins || (tw.muted ? "It is muted or bypassed, so user_text receives nothing now." : ""),
      items: [[tw.node, tw.widget, text], [node, sw, true]] });
  }
  if (!tw) {
    options.push({ id: "user_text", label: `user_text field of the Studio node (#${node.id}), use_user_text on`, current: ut.value,
      where: "user_text", note: wins, items: [[node, ut, text], [node, sw, true]] });
  }
  if (!options.length) {
    toast(`user_text gets its text from "${tw.title}", which has no text field to write into. Disconnect it or wire a text node.`);
    return null;
  }
  const pick = options.find((o) => !o.note) || options[0];
  const differs = (o) => String(o.current || "").trim() && String(o.current).trim() !== text.trim();
  let chosen = pick;
  if (options.length > 1 || differs(pick)) {
    const id = await askPick({ title: "Use on node", options, value: pick.id,
      text: "Where should the prompt go? Text that is there now is replaced; ↶ Restore previous text (or Ctrl+Z) brings it back.",
      okLabel: (o) => (differs(o) ? "Replace" : "Write") });
    if (!id) return null;
    chosen = options.find((o) => o.id === id);
  }
  const undo = { label: chosen.where, items: chosen.items.map(([n, w]) => [n, w, w.value]) };
  for (const [n, w, val] of chosen.items) writeWidget(n, w, val);
  graphChanged();
  node._kdxRender?.();
  toast(chosen.note ? `Written to ${chosen.where}. ${chosen.note}` : `Written to ${chosen.where}. Every run now picks the wildcards in it again.`,
    chosen.note ? "warn" : "success");
  return undo;
}

/** Put back what `useTextOnNode` replaced. */
export function restoreText(undo) {
  if (!undo) return;
  for (const [n, w, val] of undo.items) if (n.graph) writeWidget(n, w, val);
  graphChanged();
  for (const [n] of undo.items) n._kdxRender?.();
  toast(`Previous text of ${undo.label} restored.`, "success");
}
