/* Router, shell, actions, polling and the live progress panel. */
"use strict";

const NAV = [
  ["Workspace", [["Overview", "Overview", "home"], ["Inputs", "Inputs", "file"]]],
  ["Analysis", [["Requirements", "Requirements", "list"], ["Clarifications", "Clarifications", "help"], ["Conflicts", "Conflicts", "alert"], ["Compliance", "Compliance", "scale"], ["Risks", "Risks", "pulse"], ["SDLC", "SDLC", "flow"]]],
  ["Governance", [["Approvals", "Approvals", "stamp"], ["Audit", "Audit trail", "lock"]]],
  ["Deliver", [["Export", "Export", "download"]]],
];

/* ---------------------------------------------------------------------- render */
function navCount(page) {
  const d = D();
  if (!d) return [0, false];
  if (page === "Requirements") return [d.requirements.filter((r) => r.approval_status !== "rejected").length, false];
  if (page === "Clarifications") { const n = openQs().length; return [n, n > 0]; }
  if (page === "Conflicts") { const n = d.conflicts.filter((c) => c.status === "open").length; return [n, n > 0]; }
  if (page === "Approvals") { const n = Object.values(d.gates).filter((g) => g.status !== "approved").length; return [d.requirements.length ? n : 0, n > 0]; }
  return [0, false];
}

function shell(content) {
  const S = K.S, d = D(), running = d.job && d.job.status === "running";
  const roles = S.health?.roles || {};
  const items = NAV.flatMap(([, list]) => list);
  return `<div class="app">
    <header class="topnav">
      <div class="topnav-in">
        <div class="brand" data-act="home"><div class="logo">${I("compass", 20)}</div><div><b>KYCompass</b><span>Requirements intelligence</span></div></div>
        <div class="proj"><select class="input" id="proj-select" aria-label="Project" style="flex:1;min-width:0">${S.projects.map((p) => `<option value="${p.id}" ${p.id === S.pid ? "selected" : ""}>${esc(p.name)}</option>`).join("")}</select><button class="btn sm icon-only" data-act="home" title="New project" aria-label="New project">${I("plus", 15)}</button></div>
        ${running ? `<span class="pill accent"><span class="spin" style="width:11px;height:11px"></span> Analysing</span>` : ""}
        <div class="identity">
          <div class="engine"><span class="dot ${S.health?.llm_configured ? "ok" : "bad"}"></span><span>${S.health?.llm_configured ? "Model ready" : "No API key"}</span></div>
          <input class="input" id="id-name" value="${esc(S.identity.user)}" aria-label="Your name" placeholder="Your name">
          <select class="input" id="id-role" aria-label="Your role" style="width:auto">${Object.entries(roles).map(([k, v]) => `<option value="${k}" ${S.identity.role === k ? "selected" : ""}>${esc(v)}</option>`).join("")}</select>
          <div class="avatar">${esc(initials(S.identity.user))}</div>
          <button class="btn sm ghost icon-only" data-act="theme" aria-label="Toggle theme">${I("moon", 16)}</button>
        </div>
      </div>
      <div class="tabs-row"><nav class="tabs" aria-label="Sections">${items.map(([page, label, icon]) => { const [n, hot] = navCount(page); return `<button class="nav-item" data-go="${page}" ${S.page === page ? 'aria-current="page"' : ""}>${I(icon, 16)}<span>${label}</span>${n ? `<span class="count ${hot ? "hot" : ""}">${n}</span>` : ""}</button>`; }).join("")}</nav></div>
    </header>
    <div class="main"><main class="content" id="view">${content}</main></div></div>`;
}

function drawerContent() {
  const dr = K.S.drawer;
  if (!dr) return "";
  if (dr.type === "req") { const r = D() && reqById(dr.id); return r ? drawerHtml(r) : ""; }
  if (dr.type === "kb") return kbDrawer(K.S.kb);
  return textDrawer(dr.title, dr.subtitle, dr.body);
}

function render() {
  const S = K.S, active = document.activeElement;
  // Re-rendering replaces the DOM, so remember what the person was doing: where they had scrolled,
  // which field they were typing in, and how far down the open drawer was.
  const keep = active && (active.id || (active.dataset && active.dataset.draft))
    ? { id: active.id, draft: active.dataset && active.dataset.draft, s: active.selectionStart, e: active.selectionEnd } : null;
  const scrollY = window.scrollY, drawerEl = document.querySelector(".drawer-b"), drawerY = drawerEl ? drawerEl.scrollTop : 0;
  document.body.classList.toggle("running", !!(S.d && S.d.job && S.d.job.status === "running"));
  let html;
  if (!S.pid || !S.d) html = K.PAGES.Start();
  else {
    let page;
    try { page = (K.PAGES[S.page] || K.PAGES.Overview)(); } catch (err) { console.error(err); page = `<div class="card"><div class="card-b"><div class="callout bad">${I("alert", 16)}<div>This page failed to render: ${esc(err.message)}</div></div></div></div>`; }
    html = shell(page);
  }
  $("#root").innerHTML = html;
  $("#overlay").innerHTML = drawerContent();
  renderPanel();
  window.scrollTo(0, scrollY);
  const newDrawer = document.querySelector(".drawer-b");
  if (newDrawer && drawerEl) newDrawer.scrollTop = drawerY;
  if (keep) {
    const el = keep.id ? document.getElementById(keep.id) : document.querySelector(`[data-draft="${CSS.escape(keep.draft)}"]`);
    if (el) { el.focus({ preventScroll: true }); try { if (keep.s != null) el.setSelectionRange(keep.s, keep.e); } catch { /* not a text input */ } }
  }
}

function go(page) {
  const S = K.S;
  S.page = page; S.drawer = null; S.editing = false;
  document.body.classList.remove("nav-open");
  if (S.pid) history.replaceState(null, "", `#/${S.pid}/${page}`);
  if (page === "Audit") loadAudit();
  render();
  window.scrollTo({ top: 0 });
}

/* ------------------------------------------------------------------------ data */
async function loadProjects() { K.S.projects = await GET("/api/projects"); }
async function refresh() {
  const S = K.S;
  if (!S.pid) { await loadProjects(); render(); return; }
  try { S.d = await GET(`/api/projects/${S.pid}`); } catch (e) { S.pid = null; S.d = null; toast(e.message, true); }
  await loadProjects();
  render();
  syncPolling();
}
async function loadAudit() {
  const S = K.S;
  S.audit = await GET(`/api/projects/${S.pid}/audit?limit=300&include_llm=${S.f.auditLlm}`);
  if (S.page === "Audit") render();
}
async function openProject(id, page = "Overview") {
  const S = K.S;
  S.pid = id; S.page = page; S.drawer = null; S.audit = null;
  await refresh();
  history.replaceState(null, "", `#/${id}/${page}`);
  if (page === "Audit") loadAudit();
}

/* --------------------------------------------------------------------- polling */
let pollTimer = null;
function syncPolling() {
  const running = K.S.d && K.S.d.job && K.S.d.job.status === "running";
  if (running && !pollTimer) pollTimer = setInterval(pollJob, 1200);
  if (!running && pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}
async function pollJob() {
  const S = K.S;
  if (!S.pid) return;
  let job;
  try { job = await GET(`/api/projects/${S.pid}/job`); } catch { return; }
  if (!job || !S.d) return;
  const done = job.steps.filter((x) => x.status === "done" || x.status === "skipped").length;
  const sig = `${job.id}|${job.status}|${done}`;
  const finished = job.status !== "running";
  S.d.job = job;
  if (sig !== S.lastJobSig || finished) {
    S.lastJobSig = sig;
    if (finished) S.panelMin = job.status === "done";
    await refresh();
    if (finished) {
      if (job.status === "done") toast(job.kind === "documents" ? "Stories and use cases are ready." : "Analysis complete.");
      else toast(job.error_kind === "rate_limited" ? "Gemini's free quota ran out. Progress is saved; retry in a minute." : "Analysis failed: " + job.error, true);
    }
  } else renderPanel();
}

function renderPanel() {
  const panel = $("#runpanel"), S = K.S, job = S.d && S.d.job;
  if (job && job.status === "running") S.seenJobs.add(job.id);
  // a finished run is only worth showing if it ran during this visit; after a reload it is old news
  const hide = !job || !S.pid || S.dismissedJob === job.id || (job.status !== "running" && !S.seenJobs.has(job.id));
  panel.classList.toggle("hidden", hide);
  if (hide) return;
  const running = job.status === "running", failed = job.status === "failed";
  const title = running ? ({ analyse: "Analysing requirements", apply_answers: "Applying your answers", documents: "Writing documents" }[job.kind] || "Working") : failed ? "Stopped" : "Finished";
  const d = S.d;
  const next = !running && !failed ? (openQs().length ? `<button class="btn sm primary" data-go="Clarifications">${I("help", 14)}Review ${plural(openQs().length, "question")}</button>` : `<button class="btn sm primary" data-go="Requirements">View requirements</button>`) : "";
  panel.innerHTML = `<div class="run-h">${running ? '<span class="spin" style="color:var(--accent)"></span>' : failed ? `<span style="color:var(--bad)">${I("alert", 18)}</span>` : `<span style="color:var(--ok)">${I("check", 18)}</span>`}
    <div style="flex:1"><b>${title}</b><div class="xs muted">${fmtDur(job.elapsed)}${running ? " · model calls are paced to stay inside the free quota" : ""}</div></div>
    <button class="btn sm ghost icon-only" data-act="panel-min" aria-label="Minimise">${I("chev", 15)}</button>${running ? "" : `<button class="btn sm ghost icon-only" data-act="panel-close" aria-label="Close">${I("x", 15)}</button>`}</div>
    ${S.panelMin ? "" : `<div class="run-b">${job.message ? `<div class="run-note">${esc(job.message)}</div>` : ""}
      ${job.steps.map((s) => `<div class="run-step ${s.status}">${s.status === "running" ? '<span class="spin" style="color:var(--accent);margin-top:2px"></span>' : s.status === "done" ? `<span style="color:var(--ok)">${I("check", 15)}</span>` : s.status === "failed" ? `<span style="color:var(--bad)">${I("x", 15)}</span>` : s.status === "skipped" ? `<span class="muted">${I("check", 15)}</span>` : '<span class="dot" style="margin:6px 3px"></span>'}<div><div>${esc(s.label)}</div>${s.detail ? `<div class="detail">${esc(s.detail)}</div>` : ""}</div></div>`).join("")}
      ${failed ? `<div class="callout bad" style="margin-top:8px">${I("alert", 15)}<div>${job.error_kind === "rate_limited" ? "<b>The model's free-tier quota ran out.</b> Nothing was lost: finished stages are saved. Wait a minute, then retry to continue where it stopped." : esc(job.error)}</div></div><div class="row end" style="margin-top:8px"><button class="btn sm primary" data-act="retry-job" data-kind="${esc(job.kind)}">${I("refresh", 14)}Retry</button></div>` : ""}
      ${next ? `<div class="row end" style="margin-top:8px">${next}</div>` : ""}</div>`}`;
}

/* --------------------------------------------------------------------- actions */
const A = K.ACTIONS;
const val = (key, fb = "") => (K.S.drafts[key] ?? fb);

async function startJob(path, okMsg) {
  if (isBusy()) { toast("An analysis is already running for this project.", true); return; }
  const job = await POST(path);
  K.S.d.job = job; K.S.dismissedJob = ""; K.S.lastJobSig = ""; K.S.panelMin = false;
  if (okMsg) toast(okMsg);
  render(); syncPolling();
}

A.home = () => { K.S.pid = null; K.S.d = null; history.replaceState(null, "", "#"); loadProjects().then(render); render(); window.scrollTo({ top: 0 }); };
A.theme = () => toggleTheme();
A["scroll-to"] = (el) => document.getElementById(el.dataset.target)?.scrollIntoView({ behavior: "smooth" });
A["toggle-juris"] = (el) => { const s = K.S.jurisdictions, k = el.dataset.k; K.S.jurisdictions = s.includes(k) ? s.filter((x) => x !== k) : [...s, k]; render(); };
A["start-mode"] = (el) => { K.S.startMode = el.dataset.v; render(); };
A["input-mode"] = (el) => { K.S.inputMode = el.dataset.v; render(); };
A["fill-example"] = () => { K.S.drafts["start-text"] = EXAMPLE; if (!K.S.drafts["start-name"]) K.S.drafts["start-name"] = "Mobile account opening (example)"; render(); };
A["pick-files"] = () => $("#file-input")?.click();
A["remove-file"] = (el) => { K.S.files.splice(+el.dataset.i, 1); render(); };

async function uploadFiles(pid, files, role = "", type = "notes") {
  const fd = new FormData();
  files.forEach((f) => fd.append("files", f));
  fd.append("role", role); fd.append("source_type", type);
  const res = await api("POST", `/api/projects/${pid}/documents/upload`, fd);
  (res.errors || []).forEach((e) => toast(`${e.file}: ${e.error}`, true));
  return res.added.length;
}

A["start-analyse"] = async () => {
  const S = K.S;
  const name = val("start-name").trim() || "Untitled KYC project", text = val("start-text").trim();
  if (S.startMode === "paste" && !text) return toast("Paste some text first, or switch to Upload files.", true);
  if (S.startMode === "upload" && !S.files.length) return toast("Choose at least one file.", true);
  S.busy = true; render();
  try {
    const proj = await POST("/api/projects", { name, description: "", jurisdictions: [...S.jurisdictions, "GLOBAL"] });
    let added = 0;
    if (S.startMode === "paste") { await POST(`/api/projects/${proj.id}/documents`, { title: "Pasted notes", text, source_type: "notes", role: "" }); added = 1; }
    else added = await uploadFiles(proj.id, S.files);
    S.drafts["start-text"] = ""; S.drafts["start-name"] = ""; S.files = [];
    await openProject(proj.id);
    if (added) await startJob(`/api/projects/${proj.id}/analyse`);
  } catch (e) { toast(e.message, true); } finally { S.busy = false; render(); }
};
A["start-sample"] = async (el) => {
  K.S.busy = true; render();
  try {
    const { id } = await POST(`/api/projects/from-sample/${el.dataset.id}`);
    await openProject(id);
    await startJob(`/api/projects/${id}/analyse`);
  } catch (e) { toast(e.message, true); } finally { K.S.busy = false; render(); }
};
A["open-demo"] = async (el) => {
  K.S.busy = true; render();
  try { const { id } = await POST(`/api/demos/${el.dataset.id}`); await openProject(id); toast("Demo opened. No model calls were made."); }
  catch (e) { toast(e.message, true); } finally { K.S.busy = false; render(); }
};
A["open-project"] = (el) => openProject(el.dataset.id);
A["delete-project"] = async (el) => {
  if (!confirm("Delete this project and everything in it? This cannot be undone.")) return;
  await guard(async () => { await api("DELETE", `/api/projects/${el.dataset.id}`); await loadProjects(); render(); toast("Project deleted."); });
};

A["add-input"] = async (el) => {
  const S = K.S, run = el.dataset.run === "1";
  await guard(async () => {
    if (S.inputMode === "paste") {
      const text = val("in-text").trim();
      if (!text) return toast("Paste some text first.", true);
      await POST(`/api/projects/${S.pid}/documents`, { title: val("in-title").trim() || "Pasted notes", text, source_type: val("in-type", "notes"), role: val("in-role") });
      S.drafts["in-text"] = ""; S.drafts["in-title"] = "";
    } else {
      if (!S.files.length) return toast("Choose at least one file.", true);
      await uploadFiles(S.pid, S.files, val("in-role"), val("in-type", "notes"));
      S.files = [];
    }
    await refresh();
    toast("Input added and masked.");
    if (run) await startJob(`/api/projects/${S.pid}/analyse`);
  });
};
A["view-doc"] = async (el) => guard(async () => {
  const doc = await GET(`/api/projects/${K.S.pid}/documents/${el.dataset.id}`);
  K.S.drawer = { type: "doc", title: doc.title, subtitle: "Masked text exactly as analysed. The original is not stored.", body: `<pre class="preview">${esc(doc.text)}</pre>` };
  render();
});
A["remove-doc"] = async (el) => guard(async () => { await api("DELETE", `/api/projects/${K.S.pid}/documents/${el.dataset.id}`); await refresh(); toast("Input removed."); });

A.analyse = () => guard(() => startJob(`/api/projects/${K.S.pid}/analyse`));
A["apply-answers"] = () => guard(() => startJob(`/api/projects/${K.S.pid}/apply-answers`));
A["gen-docs"] = () => guard(() => startJob(`/api/projects/${K.S.pid}/documents-generate`));
A["retry-job"] = (el) => guard(() => startJob({ apply_answers: `/api/projects/${K.S.pid}/apply-answers`, documents: `/api/projects/${K.S.pid}/documents-generate` }[el.dataset.kind] || `/api/projects/${K.S.pid}/analyse`));
A["panel-min"] = () => { K.S.panelMin = !K.S.panelMin; renderPanel(); };
A["panel-close"] = () => { K.S.dismissedJob = K.S.d.job.id; renderPanel(); };

A["rq-status"] = (el) => { K.S.f.rqStatus = el.dataset.v; render(); };
A["rq-origin"] = (el) => { K.S.f.rqOrigin = el.dataset.v; render(); };
A["rq-weak"] = () => { K.S.f.rqWeak = !K.S.f.rqWeak; render(); };
A["rq-cat"] = (el) => { K.S.f.rqCat = el.dataset.v; render(); };
A["rq-reset"] = () => { Object.assign(K.S.f, { rqStatus: "all", rqCat: "", rqSearch: "", rqWeak: false, rqOrigin: "all" }); render(); };
A["filter-cat"] = (el) => { K.S.f.rqCat = el.dataset.cat; go("Requirements"); };

A["open-req"] = (el) => { K.S.drawer = { type: "req", id: el.dataset.id }; K.S.editing = false; render(); };
A["open-req-ref"] = (el) => { const r = reqByRef(el.dataset.ref); if (r) A["open-req"]({ dataset: { id: r.id } }); };
A["close-drawer"] = () => { K.S.drawer = null; K.S.editing = false; render(); };
A["start-edit"] = () => { K.S.editing = true; render(); };
A["cancel-edit"] = () => { K.S.editing = false; render(); };
A["save-edit"] = (el) => guard(async () => {
  const statement = $("#edit-statement").value.trim();
  await api("PATCH", `/api/projects/${K.S.pid}/requirements/${el.dataset.id}`, { statement });
  K.S.editing = false; delete K.S.drafts["edit-" + el.dataset.id];
  await refresh();
  toast("Saved. Run the analysis again to re-check this requirement.");
});
A.decide = (el) => guard(async () => {
  const r = await POST(`/api/projects/${K.S.pid}/requirements/${el.dataset.id}/decision`, { decision: el.dataset.d });
  await refresh();
  toast(`${r.ref}: ${cap(r.approval_status)}`);
});

A["pick-option"] = (el) => { K.S.drafts["q-" + el.dataset.q] = el.dataset.v; render(); };
A["answer-q"] = (el) => guard(async () => {
  const answer = val("q-" + el.dataset.q).trim();
  if (!answer) return toast("Type or pick an answer, or skip the question.", true);
  await POST(`/api/projects/${K.S.pid}/questions/${el.dataset.q}/answer`, { answer });
  delete K.S.drafts["q-" + el.dataset.q];
  await refresh();
});
A["skip-q"] = (el) => guard(async () => { await POST(`/api/projects/${K.S.pid}/questions/${el.dataset.q}/skip`); await refresh(); });
A["reopen-q"] = (el) => guard(async () => { await POST(`/api/projects/${K.S.pid}/questions/${el.dataset.q}/reopen`); await refresh(); });
A["skip-all"] = () => guard(async () => {
  if (!confirm(`Skip all ${openQs().length} open questions? They stay listed as open issues in the SRS.`)) return;
  for (const q of openQs()) await POST(`/api/projects/${K.S.pid}/questions/${q.id}/skip`);
  await refresh(); toast("Skipped. You can reopen any of them later.");
});
A["q-status"] = (el) => { K.S.f.qStatus = el.dataset.v; render(); };

A["resolve-conflict"] = (el) => guard(async () => {
  const resolution = val("cf-" + el.dataset.id).trim();
  if (resolution.length < 3) return toast("Describe how the conflict is resolved.", true);
  await POST(`/api/projects/${K.S.pid}/conflicts/${el.dataset.id}/resolve`, { resolution });
  await refresh(); toast("Resolution recorded.");
});
A["open-kb"] = () => guard(async () => { K.S.kb = K.S.kb || (await GET("/api/kb")); K.S.drawer = { type: "kb" }; render(); });
A["legal-only"] = () => { K.S.f.legalOnly = !K.S.f.legalOnly; render(); };
A["risk-cell"] = (el) => { K.S.f.riskCell = K.S.f.riskCell === el.dataset.k ? "" : el.dataset.k; render(); };
A["risk-clear"] = () => { K.S.f.riskCell = ""; render(); };
A["choose-sdlc"] = (el) => guard(async () => { await POST(`/api/projects/${K.S.pid}/sdlc/choose`, { model: el.dataset.m }); await refresh(); toast(`Workflow rebuilt for ${el.dataset.m}.`); });
A.signoff = (el) => guard(async () => {
  await POST(`/api/projects/${K.S.pid}/gates/${el.dataset.g}/signoff`, { decision: el.dataset.d });
  await refresh(); toast(`Recorded: ${el.dataset.d}.`);
});
A["audit-llm"] = () => { K.S.f.auditLlm = !K.S.f.auditLlm; loadAudit(); };
A["reload-audit"] = () => loadAudit();
A["preview-file"] = (el) => guard(async () => {
  const text = await api("GET", `/api/projects/${K.S.pid}/export/${el.dataset.f}`, undefined, { text: true });
  K.S.drawer = { type: "file", title: el.dataset.f, subtitle: "Preview", body: `<pre class="preview">${esc(text)}</pre>` };
  render();
});

/* ---------------------------------------------------------------- event wiring */
document.addEventListener("click", (e) => {
  const go_ = e.target.closest("[data-go]");
  if (go_) { go(go_.dataset.go); return; }
  const el = e.target.closest("[data-act]");
  if (!el || el.disabled) return;
  if (el.tagName === "A") return;
  const fn = A[el.dataset.act];
  if (fn) { e.stopPropagation(); fn(el, e); }
});

document.addEventListener("input", (e) => {
  const t = e.target;
  if (t.dataset && t.dataset.draft) K.S.drafts[t.dataset.draft] = t.value;
  if (t.id === "rq-search") { K.S.f.rqSearch = t.value; clearTimeout(K._st); K._st = setTimeout(render, 160); }
  if (t.id === "kb-search") { clearTimeout(K._kt); K._kt = setTimeout(render, 160); }
  if (t.id === "id-name") { K.S.identity.user = t.value.trim() || "Guest"; savePrefs(); }
});
document.addEventListener("change", (e) => {
  const t = e.target;
  if (t.id === "id-role") { K.S.identity.role = t.value; savePrefs(); render(); }
  if (t.id === "proj-select") openProject(t.value, K.S.page);
  if (t.id === "file-input") { K.S.files.push(...t.files); render(); }
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && K.S.drawer) A["close-drawer"]();
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
    const t = e.target;
    if (t.id === "start-text") A["start-analyse"]();
    if (t.dataset && t.dataset.draft === "in-text") A["add-input"]({ dataset: { run: "1" } });
    if (t.dataset && t.dataset.draft && t.dataset.draft.startsWith("q-")) A["answer-q"]({ dataset: { q: t.dataset.draft.slice(2) } });
  }
});
["dragover", "dragenter"].forEach((ev) => document.addEventListener(ev, (e) => { const d = e.target.closest(".drop"); if (d) { e.preventDefault(); d.classList.add("over"); } }));
document.addEventListener("dragleave", (e) => e.target.closest?.(".drop")?.classList.remove("over"));
document.addEventListener("drop", (e) => {
  const d = e.target.closest(".drop");
  if (!d) return;
  e.preventDefault();
  K.S.files.push(...e.dataTransfer.files);
  render();
});
window.addEventListener("blur", () => {});

/* ------------------------------------------------------------------------ boot */
async function boot() {
  loadPrefs();
  try {
    // samples and demos are optional extras: the app must still start without them
    const [health, samples, demos] = await Promise.all([GET("/api/health"), GET("/api/samples").catch(() => []), GET("/api/demos").catch(() => [])]);
    K.S.health = health; K.S.samples = samples; K.S.demos = demos;
    await loadProjects();
  } catch (e) {
    $("#root").innerHTML = `<div class="hero"><h1>Cannot reach the server</h1><p class="lede">${esc(e.message)}</p></div>`;
    return;
  }
  await routeFromHash();
}

async function routeFromHash() {
  const m = location.hash.match(/^#\/([^/]+)\/?([A-Za-z]*)/);
  if (m && K.S.projects.some((p) => p.id === m[1])) {
    const page = m[2] && K.PAGES[m[2]] ? m[2] : "Overview";
    if (K.S.pid !== m[1] || K.S.page !== page) await openProject(m[1], page);
  } else if (!m && K.S.pid) { K.S.pid = null; K.S.d = null; render(); }
  else render();
}
window.addEventListener("hashchange", routeFromHash);
boot();
