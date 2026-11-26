// KDX Wildcard Studio - KDX blue accent + light/dark tokens (one injected stylesheet).
//
// Light or dark is decided like Pixaroma's light_theme.mjs: compare the luminance of
// the page background with the page text (both written by ComfyUI from the active
// palette), not the palette's optional `light_theme` flag. Default is dark.

export const ACCENT = {
  dark: { acc: "#6f8dff", onAcc: "#060b1f", accText: "#9bb0ff" },
  light: { acc: "#2f4fd1", onAcc: "#ffffff", accText: "#2742b0" },
};

const CSS = `
.kdx-root{--kdx-acc:${ACCENT.dark.acc};--kdx-on-acc:${ACCENT.dark.onAcc};--kdx-acc-text:${ACCENT.dark.accText};
 --kdx-bg:#1b1e21;--kdx-card:#23272b;--kdx-fg:#e7e9ea;--kdx-muted:#9aa1a7;--kdx-border:#363c42;
 --kdx-off-bg:#2b3035;--kdx-off-fg:#8b9298;--kdx-warn:#f0b429;--kdx-err:#ff6b6b;--kdx-ok:#4cc38a;--kdx-field:#15181a;
 font:12px/1.35 system-ui,-apple-system,"Segoe UI",sans-serif;color:var(--kdx-fg);box-sizing:border-box}
html.kdx-light .kdx-root{--kdx-acc:${ACCENT.light.acc};--kdx-on-acc:${ACCENT.light.onAcc};--kdx-acc-text:${ACCENT.light.accText};
 --kdx-bg:#f6f7f6;--kdx-card:#ffffff;--kdx-fg:#1d211f;--kdx-muted:#4f5752;--kdx-border:#c9d0cb;
 --kdx-off-bg:#eceeed;--kdx-off-fg:#5e6661;--kdx-warn:#8a5a00;--kdx-err:#b3261e;--kdx-ok:#1e7a4c;--kdx-field:#ffffff}
.kdx-root *{box-sizing:border-box}
.kdx-panel{background:var(--kdx-bg);padding:10px;display:flex;flex-direction:column;gap:10px;min-height:100%}
.kdx-h{display:flex;align-items:center;gap:8px;font-weight:600;font-size:13px}
.kdx-h .kdx-dot{width:9px;height:9px;border-radius:50%;background:var(--kdx-acc);flex:none}
.kdx-card{background:var(--kdx-card);border:1px solid var(--kdx-border);border-radius:8px;padding:8px}
.kdx-now{border-left:3px solid var(--kdx-acc)}
.kdx-now b{color:var(--kdx-acc-text)}
.kdx-muted{color:var(--kdx-muted)}
.kdx-row{display:flex;flex-wrap:wrap;align-items:center;gap:6px}
.kdx-sp{flex:1}
.kdx-btn{appearance:none;border:1px solid var(--kdx-border);background:var(--kdx-off-bg);color:var(--kdx-fg);
 border-radius:6px;padding:3px 9px;font:inherit;cursor:pointer}
.kdx-btn:hover{border-color:var(--kdx-acc)}
.kdx-btn.kdx-primary{background:var(--kdx-acc);color:var(--kdx-on-acc);border-color:var(--kdx-acc);font-weight:600}
.kdx-seg{display:inline-flex;border:1px solid var(--kdx-border);border-radius:999px;overflow:hidden}
.kdx-seg button{appearance:none;border:0;background:transparent;color:var(--kdx-muted);padding:3px 10px;font:inherit;cursor:pointer}
.kdx-seg button.on{background:var(--kdx-acc);color:var(--kdx-on-acc);font-weight:600}
.kdx-pill{appearance:none;display:inline-flex;align-items:center;gap:5px;border-radius:999px;padding:3px 10px;
 font:inherit;cursor:pointer;border:1px solid var(--kdx-border);background:var(--kdx-off-bg);color:var(--kdx-off-fg)}
.kdx-pill.on{background:var(--kdx-acc);border-color:var(--kdx-acc);color:var(--kdx-on-acc);font-weight:600}
.kdx-pill.cur{outline:2px solid var(--kdx-fg);outline-offset:1px}
.kdx-pill:not(.on){text-decoration:line-through;text-decoration-color:var(--kdx-off-fg)}
.kdx-pill.own{border:2px dashed var(--kdx-fg)}
.kdx-cat{display:flex;flex-direction:column;gap:6px}
.kdx-cat.off{opacity:.62}
.kdx-tpls{display:flex;flex-wrap:wrap;gap:6px}
.kdx-tpl{display:inline-flex;align-items:center;gap:4px;border-radius:999px}
.kdx-rep{width:38px;border:1px solid var(--kdx-border);background:var(--kdx-field);color:var(--kdx-fg);
 border-radius:6px;padding:2px 3px;font:inherit;text-align:center}
.kdx-go{appearance:none;border:1px solid var(--kdx-border);background:var(--kdx-off-bg);color:var(--kdx-fg);cursor:pointer;
 min-height:24px;padding:2px 9px;border-radius:6px;font:inherit;font-size:11px;white-space:nowrap}
.kdx-go:hover{border-color:var(--kdx-acc);color:var(--kdx-acc-text)}
.kdx-go.on{background:var(--kdx-acc);border-color:var(--kdx-acc);color:var(--kdx-on-acc);font-weight:600}
.kdx-ico{padding:2px 6px;min-width:22px;text-align:center}
.kdx-go:focus-visible{outline:2px solid var(--kdx-acc);outline-offset:1px}
.kdx-sel{border:1px solid var(--kdx-border);background:var(--kdx-field);color:var(--kdx-fg);border-radius:6px;padding:2px 4px;font:inherit}
.kdx-num{width:110px}
.kdx-warn{color:var(--kdx-warn)}
.kdx-err{color:var(--kdx-err);font-weight:600}
.kdx-ok{color:var(--kdx-ok);font-weight:600}
.kdx-list{margin:0;padding-left:18px}
.kdx-list li.first{color:var(--kdx-acc-text);font-weight:600}
.kdx-prompt{white-space:pre-wrap;background:var(--kdx-field);border:1px solid var(--kdx-border);border-radius:6px;
 padding:6px;max-height:180px;overflow:auto;user-select:text}
.kdx-node{display:flex;flex-direction:column;gap:4px;padding:6px 8px;background:var(--kdx-card);border-radius:6px;
 border:1px solid var(--kdx-border);height:100%;overflow:hidden}
.kdx-node .kdx-line{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.kdx-node .kdx-gear{margin-left:auto}
.kdx-flash{animation:kdx-flash .6s ease-out}
@keyframes kdx-flash{from{box-shadow:0 0 0 2px var(--kdx-acc)}to{box-shadow:0 0 0 0 transparent}}
.kdx-float{position:fixed;z-index:9000;width:430px;max-width:calc(100vw - 32px);max-height:80vh;display:flex;flex-direction:column;
 border:1px solid var(--kdx-border);border-radius:10px;overflow:hidden;box-shadow:0 10px 30px rgba(0,0,0,.45);background:var(--kdx-bg)}
.kdx-float-head{display:flex;align-items:center;gap:8px;padding:6px 10px;background:var(--kdx-card);cursor:move;
 border-bottom:2px solid var(--kdx-acc);font-weight:600}
.kdx-float-body{overflow:auto}
.kdx-pill.last::before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor;opacity:.85}
.kdx-modal{position:fixed;inset:0;z-index:10000;display:flex;align-items:center;justify-content:center;
 background:rgba(0,0,0,.5);padding:16px}
.kdx-modal-box{width:min(420px,100%);background:var(--kdx-card);border:1px solid var(--kdx-border);border-radius:10px;
 border-top:3px solid var(--kdx-acc);padding:14px;display:flex;flex-direction:column;gap:10px;
 box-shadow:0 14px 40px rgba(0,0,0,.5);font-size:13px}
.kdx-modal-title{font-weight:600;font-size:14px}
.kdx-modal-text{color:var(--kdx-muted);white-space:pre-wrap}
.kdx-field{width:100%;border:1px solid var(--kdx-border);background:var(--kdx-field);color:var(--kdx-fg);border-radius:6px;
 padding:6px 8px;font:inherit;resize:vertical}
.kdx-field:focus{outline:2px solid var(--kdx-acc);outline-offset:0}
.kdx-btn.kdx-danger{background:var(--kdx-err);border-color:var(--kdx-err);color:#fff;font-weight:600}
.kdx-btn:disabled,.kdx-go:disabled{opacity:.45;cursor:not-allowed}
.kdx-gal{position:fixed;inset:0;z-index:9500;background:var(--kdx-bg);display:flex;flex-direction:column}
.kdx-gal-head{display:flex;flex-wrap:wrap;align-items:center;gap:8px;padding:8px 12px;background:var(--kdx-card);
 border-bottom:2px solid var(--kdx-acc);flex:none}
.kdx-gal-title{font-weight:600;font-size:14px}
.kdx-gal-body{flex:1;overflow:auto;padding:4px 14px 20px}
.kdx-gal-cat{font-size:15px;margin:16px 0 4px;padding-bottom:3px;border-bottom:1px solid var(--kdx-border)}
.kdx-gal-tpls{display:flex;flex-wrap:wrap;gap:6px 18px;align-items:flex-start}
.kdx-gal-tpl{max-width:100%}
.kdx-gal-tpl h3{font-size:12px;font-weight:600;margin:10px 0 4px;color:var(--kdx-acc-text)}
.kdx-gal-row{display:flex;flex-wrap:wrap;gap:8px}
.kdx-gal-cell{appearance:none;border:1px solid var(--kdx-border);background:var(--kdx-card);color:var(--kdx-fg);border-radius:6px;
 padding:3px;display:flex;flex-direction:column;gap:3px;cursor:zoom-in;font:inherit}
.kdx-gal-cell:hover,.kdx-gal-cell:focus-visible{border-color:var(--kdx-acc);outline:none}
.kdx-gal-cell img{object-fit:cover;border-radius:4px;display:block;background:var(--kdx-field)}
.kdx-gal-cap{font-size:11px;color:var(--kdx-muted);text-align:left;padding:0 2px}
.kdx-bb-body{flex:1;min-height:0;display:grid;grid-template-columns:minmax(230px,280px) minmax(380px,1fr) minmax(300px,380px);gap:10px;padding:10px}
.kdx-bb-col{overflow:auto;min-height:0;display:flex;flex-direction:column;gap:8px;padding-right:2px}
.kdx-bb-col > *{flex:none}
.kdx-bb-palette{overflow:hidden}
.kdx-bb-palhead{flex:none;display:flex;flex-direction:column;gap:6px}
.kdx-bb-tabs{align-self:flex-start;flex:none}
.kdx-bb-pallist{flex:1 1 0;min-height:0;overflow:auto;display:flex;flex-direction:column;gap:6px;padding-right:2px}
.kdx-bb-pallist > *{flex:none}
.kdx-bb-tree details{border-bottom:1px solid var(--kdx-border);padding:2px 0}
.kdx-bb-tree summary{cursor:pointer;font-weight:600;padding:2px 0}
.kdx-bb-dirnew{visibility:hidden;margin-left:4px}
.kdx-bb-tree summary:hover .kdx-bb-dirnew,.kdx-bb-dirnew:focus-visible{visibility:visible}
.kdx-bb-tree summary:focus-visible{outline:2px solid var(--kdx-acc)}
.kdx-bb-pal{border:1px solid var(--kdx-border);background:var(--kdx-card);border-radius:8px;padding:5px 7px;cursor:grab;display:flex;
 flex-direction:column;gap:2px}
.kdx-bb-pal:hover{border-color:var(--kdx-acc)}
.kdx-bb-pal.dragging{opacity:.45}
.kdx-bb-palpool{flex-direction:row;align-items:center;gap:6px;border-radius:999px;padding:1px 3px 1px 10px;margin:2px 0 2px 8px;
 font:12px ui-monospace,Consolas,monospace;border-color:var(--kdx-acc)}
.kdx-bb-palpool span:first-child{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.kdx-bb-palpool.sel{background:var(--kdx-acc);color:var(--kdx-on-acc)}
.kdx-bb-palpool.sel .kdx-muted{color:var(--kdx-on-acc)}
.kdx-bb-palsn .kdx-bb-sum{font:11px ui-monospace,Consolas,monospace}
.kdx-bb-palshape{position:relative;padding-right:32px}
.kdx-bb-palshape .kdx-go{position:absolute;right:5px;top:5px}
.kdx-bb-tools{flex-wrap:wrap}
.kdx-bb-canvas{background:var(--kdx-card);border:1px solid var(--kdx-border);border-radius:10px;padding:12px;min-height:200px;line-height:2.1}
.kdx-bb-lane{display:flex;flex-wrap:wrap;align-items:center;gap:3px 2px;min-height:26px;min-width:40px;flex:1}
.kdx-bb-canvas > .kdx-bb-lane{min-height:160px;align-content:flex-start}
.kdx-bb-empty{color:var(--kdx-muted);font-style:italic;padding:0 6px}
.kdx-bb-n{position:relative;display:inline-flex;align-items:center;border-radius:8px;line-height:1.4;cursor:pointer;max-width:100%}
.kdx-bb-n.dragging{opacity:.4}
.kdx-bb-n.sel{box-shadow:0 0 0 2px var(--kdx-acc)}
.kdx-bb-n:focus-visible{outline:2px solid var(--kdx-acc);outline-offset:1px}
.kdx-bb-text,.kdx-bb-raw{border:1px dashed var(--kdx-border);background:var(--kdx-bg);padding:1px 4px 1px 0}
.kdx-bb-raw{border-color:var(--kdx-warn);font-family:ui-monospace,Consolas,monospace}
.kdx-bb-grip{cursor:grab;color:var(--kdx-muted);padding:0 3px 0 4px;font-size:10px;user-select:none}
.kdx-bb-tv{white-space:pre-wrap;outline:none;min-width:6px;cursor:text;word-break:break-word}
.kdx-bb-tv:focus{background:var(--kdx-field);box-shadow:0 0 0 1px var(--kdx-acc);border-radius:3px}
.kdx-bb-pool{border:1px solid var(--kdx-acc);background:color-mix(in srgb,var(--kdx-acc) 16%,var(--kdx-card));padding:1px 9px;
 border-radius:999px;font:12px ui-monospace,Consolas,monospace;cursor:grab}
.kdx-bb-pool b{color:var(--kdx-acc-text)}
.kdx-bb-pool.bad{border-color:var(--kdx-err)}
.kdx-bb-dir{color:var(--kdx-muted);font-size:10px}
.kdx-bb-solo{border:1px dotted var(--kdx-border);border-radius:999px;padding:0 2px;cursor:grab}
.kdx-bb-solo > .kdx-bb-lane{flex:none;min-height:0;min-width:0}
.kdx-bb-choice{flex-direction:column;align-items:stretch;border:1px solid var(--kdx-border);border-left:4px solid var(--kdx-acc);
 background:var(--kdx-bg);padding:2px 6px 4px;gap:3px;cursor:grab;margin:2px 0}
.kdx-bb-some{border-left-style:dashed}
.kdx-bb-multi{border-left-style:double;border-left-width:6px}
.kdx-bb-ch{display:flex;align-items:center;gap:5px;font-size:11px;font-weight:600;color:var(--kdx-acc-text)}
.kdx-bb-ch .kdx-muted{font-weight:400}
.kdx-bb-opt{display:flex;align-items:center;gap:4px;border-top:1px solid var(--kdx-border);padding-top:3px}
.kdx-bb-w{width:30px;border:1px solid var(--kdx-border);background:var(--kdx-field);color:var(--kdx-fg);border-radius:4px;font:11px ui-monospace,Consolas,monospace;text-align:center}
.kdx-bb-w:focus{outline:2px solid var(--kdx-acc)}
.kdx-bb-fold,.kdx-bb-ox,.kdx-bb-add,.kdx-bb-x{appearance:none;border:0;background:transparent;color:var(--kdx-muted);cursor:pointer;font:inherit;padding:0 3px;border-radius:4px}
.kdx-bb-fold:hover,.kdx-bb-ox:hover,.kdx-bb-add:hover,.kdx-bb-x:hover{color:var(--kdx-acc-text)}
.kdx-bb-add{align-self:flex-start;font-size:11px}
.kdx-bb-x{display:none;font-size:10px;padding:0 2px 0 4px}
.kdx-bb-n:hover > .kdx-bb-x,.kdx-bb-n.sel > .kdx-bb-x,.kdx-bb-ch .kdx-bb-x{display:inline}
.kdx-bb-ch .kdx-bb-x{visibility:hidden}
.kdx-bb-choice:hover > .kdx-bb-ch .kdx-bb-x,.kdx-bb-choice.sel > .kdx-bb-ch .kdx-bb-x{visibility:visible}
.kdx-bb-caret{display:inline-block;width:3px;height:22px;background:var(--kdx-acc);border-radius:2px;margin:0 1px;flex:none}
.kdx-bb-insp{display:flex;flex-direction:column;gap:6px;border-top:3px solid var(--kdx-acc)}
.kdx-bb-head{font-style:italic}
.kdx-bb-vals{margin:0;padding-left:28px;max-height:300px;overflow:auto;font-size:11px}
.kdx-bb-text,.kdx-bb-sample{white-space:pre-wrap;word-break:break-word;background:var(--kdx-field);border:1px solid var(--kdx-border);
 border-radius:6px;padding:6px 8px;margin-top:4px}
.kdx-bb-text,.kdx-bb-ta{font:11px/1.45 ui-monospace,Consolas,monospace}
.kdx-bb-ta{resize:vertical}
.kdx-bb-line summary{cursor:pointer;font-weight:600}
.kdx-pe{z-index:10000}
.kdx-pe-box{width:min(1100px,96vw);max-height:92vh;display:flex;flex-direction:column;gap:8px}
.kdx-pe-box textarea{resize:vertical}
.kdx-pe-main{flex:1;min-height:0;display:grid;grid-template-columns:minmax(0,1.4fr) minmax(260px,1fr);gap:12px}
.kdx-pe-list,.kdx-pe-side{overflow:auto;min-height:120px;max-height:60vh;display:flex;flex-direction:column;gap:4px;padding-right:2px}
.kdx-pe-list > *,.kdx-pe-side > *{flex:none}
.kdx-pe-row{display:flex;align-items:center;gap:4px}
.kdx-pe-row.dragging{opacity:.4}
.kdx-pe-v{flex:1;min-width:0;font:12px ui-monospace,Consolas,monospace;padding:3px 6px}
.kdx-pe-c .kdx-pe-cv{font-style:italic;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.kdx-pe-caret{height:3px;background:var(--kdx-acc);border-radius:2px;flex:none}
@media (max-width:800px){.kdx-pe-main{grid-template-columns:1fr}}
@media (max-width:1100px){.kdx-bb-body{grid-template-columns:240px 1fr;grid-template-rows:minmax(260px,1fr) auto;overflow:auto}
 .kdx-bb-col[data-col="side"]{grid-column:1 / -1;overflow:visible}}
@media (prefers-reduced-motion:reduce){.kdx-flash{animation:none}}
.kdx-pk-body{flex:1;overflow:auto;padding:12px 16px 24px;display:flex;flex-direction:column;gap:12px;max-width:1100px;width:100%;box-sizing:border-box;margin:0 auto}
.kdx-pk-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:10px}
.kdx-pk-card{display:flex;flex-direction:column;gap:6px}
.kdx-pk-card h3{margin:0;font-size:14px}
.kdx-pk-tag{display:inline-block;border:1px solid var(--kdx-border);border-radius:999px;padding:0 7px;font-size:11px;color:var(--kdx-muted)}
.kdx-pk-tag.nsfw{border-color:var(--kdx-warn);color:var(--kdx-warn)}
.kdx-pk-form{display:grid;grid-template-columns:110px 1fr;gap:6px 10px;align-items:center}
.kdx-pk-form label{color:var(--kdx-muted)}
.kdx-pk-list{max-height:260px;overflow:auto;border:1px solid var(--kdx-border);border-radius:6px;padding:4px 8px;background:var(--kdx-field);
 display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:2px 12px}
.kdx-pk-list label{display:flex;gap:6px;align-items:center;cursor:pointer;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.kdx-pk-msgs{margin:0;padding-left:18px;font-size:12px}
.kdx-pk-msgs li{margin:2px 0}
.kdx-pk-tbl{border-collapse:collapse;font-size:12px;width:100%}
.kdx-pk-tbl td,.kdx-pk-tbl th{text-align:left;padding:2px 8px;border-bottom:1px solid var(--kdx-border)}
.kdx-pk-tbl code{font:11px ui-monospace,Consolas,monospace}
.kdx-pk-sample{white-space:pre-wrap;word-break:break-word;background:var(--kdx-field);border:1px solid var(--kdx-border);border-radius:6px;padding:6px 8px;margin:4px 0;font-size:12px}
.kdx-pk-drop{border:2px dashed var(--kdx-border);border-radius:8px;padding:18px;text-align:center;color:var(--kdx-muted)}
.kdx-pk-drop.over{border-color:var(--kdx-acc);color:var(--kdx-acc-text)}
`;

let injected = false;

function luminance(color) {
  const m = String(color).match(/\d+(\.\d+)?/g);
  if (!m || m.length < 3) return null;
  const [r, g, b] = m.slice(0, 3).map((v) => {
    const c = Number(v) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function detectLight() {
  try {
    const cs = getComputedStyle(document.body);
    const bg = luminance(cs.backgroundColor);
    const fg = luminance(cs.color);
    const light = bg != null && fg != null && bg > fg;
    document.documentElement.classList.toggle("kdx-light", light);
  } catch (_e) { /* keep dark */ }
}

export function ensureTheme() {
  if (injected) return;
  injected = true;
  const st = document.createElement("style");
  st.id = "kdx-console-style";
  st.textContent = CSS;
  document.head.appendChild(st);
  detectLight();
  // ComfyUI rewrites the palette as inline style on <html> when the theme changes.
  new MutationObserver(() => detectLight()).observe(document.documentElement, {
    attributes: true, attributeFilter: ["style"],
  });
}
