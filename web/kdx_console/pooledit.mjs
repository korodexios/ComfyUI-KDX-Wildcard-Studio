// KDX Wildcard Studio - Pool editor (Template builder, phase 2): create a pool, edit its values, weights and order, retire
// values or the whole pool. Nothing is deleted: the server moves what leaves a pool into wildcards_archive/ (outside
// the library) and keeps <pool>.txt.bak. Every rule is checked on the server; this window only edits the list.
import { call, toast } from "./client.mjs?v=0.7.13";
import { askConfirm } from "./dialog.mjs?v=0.7.13";
import { NEW_FOLDER, newPoolKey, startFolder } from "./poolname.mjs?v=0.7.13";

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

/**
 * Open the editor (a modal over the builder). `key` = an existing pool, or null for a new one (`folder` preselected).
 * `folders` = existing folders for a new pool; `onSaved(key)` runs after a save or a retire.
 */
export async function openPoolEditor({ key = null, folder = "", folders = [], onSaved = () => {} }) {
  const isNew = !key;
  const v = {
    key, nk: { choice: startFolder(folder, folders), typed: "", name: "" }, desc: "", lines: [], retired: [], users: null, file: "",
    archive: "", warnings: null, samples: [], template: null, dirty: false, busy: false,
  };
  if (!isNew) {
    const r = await call("GET", `/kdx_console/builder/pool/edit?key=${encodeURIComponent(key)}`);
    if (!r.ok) { toast(r.error); return; }
    Object.assign(v, { desc: r.pool.desc, lines: r.pool.lines.map((ln) => ({ ...ln, id: Math.random(), o: true })), users: r.users, file: r.file, archive: r.archive });
  } else {
    v.lines = [{ v: "", w: null, id: Math.random() }];
  }
  const wrap = document.createElement("div");
  wrap.className = "kdx-root kdx-modal kdx-pe";
  document.body.appendChild(wrap);
  const fullKey = () => (isNew ? newPoolKey(v.nk).key : v.key);
  const model = () => ({ key: fullKey(), new: isNew, desc: v.desc, lines: v.lines.map((ln) => ("c" in ln ? { c: ln.c } : { v: ln.v, w: ln.w || null })) });

  // ------------------------------------------------------------------ rendering
  function headHtml() {
    if (!isNew) {
      return `<div class="kdx-row"><span class="kdx-modal-title">✎ Pool <span class="kdx-acc-t">${esc(v.key)}</span></span><span class="kdx-sp"></span>
        <span class="kdx-muted" title="The file in the wildcard folder">${esc(v.file)}</span></div>`;
    }
    const k = newPoolKey(v.nk);
    return `<div class="kdx-row"><span class="kdx-modal-title">＋ New pool</span></div>
      <div class="kdx-row kdx-pe-new" style="flex-wrap:wrap">
        <label class="kdx-row" style="gap:3px" title="The folder the pool goes into">folder
          <select class="kdx-sel" data-p="fsel"><option value="" ${v.nk.choice ? "" : "selected"} disabled>choose a folder…</option>
            ${folders.map((f) => `<option value="${esc(f)}" ${v.nk.choice === f ? "selected" : ""}>${esc(f)}</option>`).join("")}
            <option value="${NEW_FOLDER}" ${v.nk.choice === NEW_FOLDER ? "selected" : ""}>＋ New folder…</option></select></label>
        ${v.nk.choice === NEW_FOLDER ? `<label class="kdx-row" style="gap:3px" title="a-z, 0-9, _ and -; a / makes a subfolder">new folder
          <input class="kdx-sel" data-p="fnew" value="${esc(v.nk.typed)}" placeholder="auto or auto/motor" style="width:150px" spellcheck="false"></label>` : ""}
        <label class="kdx-row" style="gap:3px" title="File name: lower case letters, digits and _">name
          <input class="kdx-sel" data-p="name" value="${esc(v.nk.name)}" placeholder="light_window" style="width:160px" spellcheck="false"></label></div>
      ${v.nk.choice === NEW_FOLDER ? `<div class="kdx-muted">New folder: lower case letters, digits, _ and -; a / makes a subfolder (auto/motor).</div>` : ""}
      <div class="kdx-row" data-pp="token">${tokenHtml(k)}</div>`;
  }
  function tokenHtml(k) {
    return k.error ? `<span class="kdx-warn">${esc(k.error)}</span>${k.token ? ` <span class="kdx-muted">(so far: ${esc(k.token)})</span>` : ""}`
      : `<span class="kdx-muted">Creates</span> <code class="kdx-acc-t">${esc(k.token)}</code> <span class="kdx-muted">(${esc(k.key)}.txt); use this token in templates.</span>`;
  }
  function rowHtml(ln, i) {
    if ("c" in ln) {
      return `<div class="kdx-pe-row kdx-pe-c" data-i="${i}"><span class="kdx-bb-grip" draggable="true" title="Drag to move">⠿</span>
        <span class="kdx-muted kdx-pe-cv" title="A comment in the file: kept where it is">#${esc(ln.c)}</span><span class="kdx-sp"></span>
        <button class="kdx-bb-ox" data-p="rmc" data-i="${i}" title="Remove this comment">✕</button></div>`;
    }
    return `<div class="kdx-pe-row" data-i="${i}"><span class="kdx-bb-grip" draggable="true" title="Drag to change the order">⠿</span>
      <input class="kdx-bb-w" data-p="w" data-i="${i}" value="${esc(ln.w ?? "")}" placeholder="1" inputmode="decimal" title="Weight: 3 = three times as often as a value with 1">
      <input class="kdx-field kdx-pe-v" data-p="v" data-i="${i}" value="${esc(ln.v)}" spellcheck="false" placeholder="a value, lower case, no full stop at the end">
      <button class="kdx-bb-ox" data-p="retire" data-i="${i}" title="Retire this value (it moves into the archive when you save)">✕</button></div>`;
  }
  function listHtml() {
    return `${v.lines.map(rowHtml).join("")}
      <div class="kdx-row"><button class="kdx-btn" data-p="add" title="Add a value at the end">＋ value</button><span class="kdx-muted">${v.lines.filter((l) => !("c" in l)).length} values</span>
      <span class="kdx-sp"></span>${v.retired.length ? `<span class="kdx-muted">${v.retired.length} to retire: ${v.retired.map((r) => `<s>${esc(r.v.slice(0, 30))}</s>`).join(", ")}</span>
      <button class="kdx-btn" data-p="unretire" title="Bring the retired values back">↶</button>` : ""}</div>`;
  }
  function sideHtml() {
    const u = v.users;
    const users = isNew ? `<div class="kdx-muted">A new pool: no template uses it yet. Drag it into a template after saving.</div>`
      : `<div><b>Used by</b> ${u.templates.length ? u.templates.map(esc).join(", ") : "no template directly"}${u.hidden ? ` <span class="kdx-muted">(+${u.hidden} NSFW hidden)</span>` : ""}</div>
         ${u.pools.length ? `<div><b>Inside pools</b> ${u.pools.map(esc).join(", ")}</div>` : ""}
         ${u.reach.length > u.templates.length ? `<div class="kdx-muted">Through other pools it reaches ${u.reach.length} template(s): ${u.reach.slice(0, 12).map(esc).join(", ")}${u.reach.length > 12 ? " …" : ""}</div>` : ""}`;
    const w = v.warnings;
    const checks = w == null ? `<p class="kdx-muted">Checking…</p>` : w.length ? w.map((x) => `<div class="${x.level === "error" ? "kdx-err" : "kdx-warn"}">${x.level === "error" ? "⛔" : "⚠"} ${esc(x.msg)}</div>`).join("")
      : `<div class="kdx-ok">✅ all rules met</div>`;
    return `${users}<div class="kdx-row"><b>Checks</b></div>${checks}
      <div class="kdx-row"><b>3 prompts</b><span class="kdx-muted">${v.template ? `from ${esc(v.template)}` : "of the pool alone"}</span><span class="kdx-sp"></span>
        <button class="kdx-btn" data-p="again" title="New random prompts">⟳</button></div>
      ${v.samples.map((s) => `<div class="kdx-bb-sample">${esc(s.text)}</div>`).join("")}
      ${isNew ? "" : `<div class="kdx-muted">Removed values go to ${esc(v.archive)}; the old file is kept as .bak.</div>`}`;
  }
  function render() {
    const errors = (v.warnings || []).filter((x) => x.level === "error").length;
    const canRetire = !isNew && v.users && !v.users.templates.length && !v.users.pools.length && !v.users.hidden;
    wrap.innerHTML = `<div class="kdx-modal-box kdx-pe-box" role="dialog" aria-modal="true" aria-label="Pool editor"><div data-pp="head">${headHtml()}</div>
      <label class="kdx-muted">Description (comment lines at the top of the file: what the pool holds, which slot it fills)
        <textarea class="kdx-field" data-p="desc" rows="2" spellcheck="false">${esc(v.desc)}</textarea></label>
      <div class="kdx-pe-main"><div class="kdx-pe-list" data-pp="list">${listHtml()}</div><div class="kdx-pe-side" data-pp="side">${sideHtml()}</div></div>
      <div class="kdx-row kdx-modal-btns">${isNew ? "" : `<button class="kdx-btn kdx-danger" data-p="retirepool" ${canRetire ? "" : "disabled"}
        title="${canRetire ? "Move the whole pool into the archive" : "Only a pool that no template or pool uses can be retired"}">Retire pool</button>`}
        <span class="kdx-sp"></span><button class="kdx-btn" data-p="cancel">Cancel</button>
        <button class="kdx-btn kdx-primary" data-p="save" ${errors ? "disabled" : ""} title="${errors ? "Fix the errors (⛔) first" : "Write the pool (the old file is kept as .bak)"}">${isNew ? "Create pool" : "Save pool"}</button></div></div>`;
  }
  const paint = (pp, html) => { const el = wrap.querySelector(`[data-pp="${pp}"]`); if (el) { const t = el.scrollTop; el.innerHTML = html(); el.scrollTop = t; } };
  function paintSide() {
    paint("side", sideHtml);
    const errors = (v.warnings || []).filter((x) => x.level === "error").length;
    const save = wrap.querySelector('[data-p="save"]');
    if (save) { save.disabled = !!errors; save.title = errors ? "Fix the errors (⛔) first" : "Write the pool (the old file is kept as .bak)"; }
  }

  // ------------------------------------------------------------------ server
  let timer = null;
  let ticket = 0;
  let seed = Math.floor(Math.random() * 2 ** 31);
  const schedule = (d = 400) => { clearTimeout(timer); timer = setTimeout(runCheck, d); };
  async function runCheck() {
    const my = ++ticket;
    const nk = isNew ? newPoolKey(v.nk) : null;
    if (nk?.error) { v.warnings = [{ level: "error", msg: nk.error }]; v.samples = []; paintSide(); return; }
    const r = await call("POST", "/kdx_console/builder/pool/check", { ...model(), seed });
    if (my !== ticket || !wrap.isConnected) return;
    if (!r.ok) { v.warnings = [{ level: "error", msg: r.error }]; v.samples = []; }
    else { v.warnings = r.warnings; v.samples = r.samples; v.template = r.template; if (!isNew) v.users = r.users; }
    paintSide();
  }
  const changed = (repaintList = false) => { v.dirty = true; v.warnings = null; if (repaintList) paint("list", listHtml); schedule(); };

  async function save() {
    clearTimeout(timer);
    await runCheck();
    if ((v.warnings || []).some((x) => x.level === "error")) { toast("Fix the errors (⛔) first."); return; }
    const warns = v.warnings || [];
    if (warns.length && !(await askConfirm({ title: `Save with ${warns.length} warning${warns.length === 1 ? "" : "s"}?`, text: warns.map((x) => `• ${x.msg}`).join("\n"), okLabel: "Save anyway" }))) return;
    if (v.retired.length && !(await askConfirm({ title: `Retire ${v.retired.length} value${v.retired.length === 1 ? "" : "s"}?`,
      text: `They leave the pool and are appended to ${v.archive} with today's date. Nothing is deleted.`, okLabel: "Save and retire" }))) return;
    const r = await call("POST", "/kdx_console/builder/pool/save", model());
    if (!r.ok) { toast(r.error); return; }
    toast(`${r.created ? "Created" : "Saved"} ${r.key}${r.archived ? ` · ${r.archived} value(s) moved to the archive` : ""}${r.backup ? " · old file kept as .bak" : ""}.`, "success");
    v.dirty = false;
    close();
    onSaved(r.key);
  }
  async function retirePool() {
    if (!(await askConfirm({ title: `Retire the whole pool ${v.key}?`, danger: true, okLabel: "Retire pool",
      text: `No template or pool uses it. Every line is appended to ${v.archive}, then the pool leaves the library.` }))) return;
    const r = await call("POST", "/kdx_console/builder/pool/retire", { key: v.key });
    if (!r.ok) { if (r.users) { v.users = r.users; paintSide(); } toast(r.error); return; }
    toast(`Retired ${r.key} (${r.lines} lines in the archive).`, "success");
    v.dirty = false;
    close();
    onSaved(null);
  }

  // ------------------------------------------------------------------ events
  wrap.addEventListener("input", (e) => {
    const t = e.target;
    const p = t.dataset.p;
    if (p === "v") { v.lines[Number(t.dataset.i)].v = t.value; changed(); }
    else if (p === "w") { v.lines[Number(t.dataset.i)].w = t.value.trim() || null; changed(); }
    else if (p === "desc") { v.desc = t.value; v.dirty = true; }
    else if (p === "name" || p === "fnew") { // update the token line only: never repaint the field being typed in
      v.nk[p === "name" ? "name" : "typed"] = t.value;
      v.dirty = true;
      paint("token", () => tokenHtml(newPoolKey(v.nk)));
      schedule();
    }
  });
  wrap.addEventListener("change", (e) => {
    if (e.target.dataset.p !== "fsel") return;
    v.nk.choice = e.target.value;
    v.dirty = true;
    paint("head", headHtml);
    wrap.querySelector(v.nk.choice === NEW_FOLDER ? '[data-p="fnew"]' : '[data-p="name"]')?.focus();
    schedule(0);
  });
  wrap.addEventListener("click", async (e) => {
    const b = e.target.closest("[data-p]");
    const p = b?.dataset.p;
    if (!p || b.tagName === "INPUT" || b.tagName === "TEXTAREA") return;
    if (p === "cancel") { if (!v.dirty || await askConfirm({ title: "Discard the changes to this pool?", okLabel: "Discard", danger: true })) close(); }
    else if (p === "save") save();
    else if (p === "retirepool") retirePool();
    else if (p === "again") { seed = Math.floor(Math.random() * 2 ** 31); runCheck(); }
    else if (p === "add") {
      v.lines.push({ v: "", w: null, id: Math.random() });
      changed(true);
      const inputs = wrap.querySelectorAll('[data-p="v"]');
      inputs[inputs.length - 1]?.focus();
    } else if (p === "retire") {
      const [ln] = v.lines.splice(Number(b.dataset.i), 1);
      if (ln.o && ln.v.trim()) v.retired.push(ln); // only what is in the file goes to the archive
      changed(true);
    } else if (p === "rmc") { v.lines.splice(Number(b.dataset.i), 1); changed(true); }
    else if (p === "unretire") { v.lines.push(...v.retired); v.retired = []; changed(true); }
  });
  // drag to reorder (by the ⠿ grip)
  let dragI = null;
  let caret = null;
  wrap.addEventListener("dragstart", (e) => {
    const row = e.target.closest?.(".kdx-pe-row");
    if (!row || !e.target.classList.contains("kdx-bb-grip")) return;
    dragI = Number(row.dataset.i);
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", "kdx-pool-line");
    e.stopPropagation();
    row.classList.add("dragging");
  });
  const dropIndex = (e) => {
    const rows = [...wrap.querySelectorAll(".kdx-pe-row")];
    const i = rows.findIndex((r) => { const b = r.getBoundingClientRect(); return e.clientY < b.top + b.height / 2; });
    return { rows, i: i < 0 ? rows.length : i };
  };
  wrap.addEventListener("dragover", (e) => {
    if (dragI == null) return;
    e.preventDefault();
    e.stopPropagation();
    const { rows, i } = dropIndex(e);
    if (!caret) { caret = document.createElement("div"); caret.className = "kdx-pe-caret"; }
    const list = wrap.querySelector(".kdx-pe-list");
    list.insertBefore(caret, rows[i] || list.querySelector(".kdx-pe-list > .kdx-row"));
  });
  wrap.addEventListener("drop", (e) => {
    if (dragI == null) return;
    e.preventDefault();
    e.stopPropagation();
    let { i } = dropIndex(e);
    caret?.remove();
    const [ln] = v.lines.splice(dragI, 1);
    if (i > dragI) i -= 1;
    v.lines.splice(i, 0, ln);
    dragI = null;
    changed(true);
  });
  wrap.addEventListener("dragend", () => { dragI = null; caret?.remove(); });
  wrap.addEventListener("keydown", async (e) => {
    e.stopPropagation(); // the builder and ComfyUI must not see these keys
    if (e.key === "Escape") {
      e.preventDefault();
      if (!v.dirty || await askConfirm({ title: "Discard the changes to this pool?", okLabel: "Discard", danger: true })) close();
    } else if (e.key === "Enter" && e.target.dataset?.p === "v") { // Enter in a value adds the next one below
      e.preventDefault();
      const i = Number(e.target.dataset.i);
      v.lines.splice(i + 1, 0, { v: "", w: null, id: Math.random() });
      changed(true);
      wrap.querySelector(`[data-p="v"][data-i="${i + 1}"]`)?.focus();
    }
  });
  function close() { clearTimeout(timer); wrap.remove(); }
  render();
  wrap.querySelector(!isNew ? '[data-p="v"]' : v.nk.choice ? '[data-p="name"]' : '[data-p="fsel"]')?.focus();
  runCheck();
}
