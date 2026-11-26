// KDX Wildcard Studio - frontend entry: sidebar tab + node body. One small hook (client.mjs): the template picked with ▶ is attached to the next queued prompt.
import { app } from "../../scripts/app.js";
import { setupNode } from "./kdx_console/node.mjs?v=0.7.8";
import { mountPanel } from "./kdx_console/panel.mjs?v=0.7.8";

app.registerExtension({
  name: "KDX.Studio",

  async setup() {
    const em = app.extensionManager;
    if (em?.registerSidebarTab) {
      em.registerSidebarTab({
        id: "kdx-console",
        icon: "pi pi-sliders-h",
        title: "KDX Wildcard Studio",
        tooltip: "KDX Wildcard Studio – categories and templates",
        type: "custom",
        render: (el) => {
          el.innerHTML = "";
          return mountPanel(el);
        },
      });
    }
  },

  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData?.name !== "KDX_Console") return;
    const onCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function (...a) {
      const r = onCreated?.apply(this, a);
      setupNode(this);
      const [w, h] = this.size || [0, 0];
      this.setSize?.([Math.max(w, 300), Math.max(h, 120)]);
      return r;
    };
    // Repaint after load (the pin may have come from an image). Read-only: no writes here.
    const onConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function (...a) {
      const r = onConfigure?.apply(this, a);
      this._kdxRender?.();
      return r;
    };
  },
});
