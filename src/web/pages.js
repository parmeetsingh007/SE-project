/* Pages part 1: landing, overview, inputs, requirements (+ drawer), clarifications. */
"use strict";

const D = () => K.S.d;
const isBusy = () => !!(K.S.d && K.S.d.job && K.S.d.job.status === "running");
const reqById = (id) => D().requirements.find((r) => r.id === id);
const reqByRef = (ref) => D().requirements.find((r) => r.ref === ref);
const draft = (key, fallback = "") => (K.S.drafts[key] !== undefined ? K.S.drafts[key] : fallback);
const live = () => D().requirements.filter((r) => r.approval_status !== "rejected");
const questionsOf = (rid) => D().questions.filter((q) => q.requirement_id === rid);
const openQs = () => D().questions.filter((q) => q.status === "open");
const unappliedAnswers = () => D().questions.filter((q) => q.status === "answered" && !q.applied);
const youCan = (gateRoles) => gateRoles.includes(K.S.identity.role);
const roleName = (r) => (K.S.health?.roles || {})[r] || cap(r);
const EXAMPLE = `Priya (Product Manager): We want people to open a savings account on their phone, quickly, without visiting a branch. Something like a few minutes, I'm not sure what the target should be. It has to feel easy and secure. We'll probably do a selfie or a video call, we haven't decided. Risky customers should get extra checks but I don't know how we decide who is risky.

Arjun (Compliance): We must follow the RBI KYC rules and keep records for the required period, I think five years but please don't quote me. We need some kind of consent and sanctions screening. I can't give a final answer on video KYC yet.`;

/* ============================================================== landing / start */
K.PAGES.Start = () => {
  const S = K.S, h = S.health || {};
  const juris = Object.entries(h.jurisdictions || { IN: "India", EU: "European Union", US: "United States" }).filter(([k]) => k !== "GLOBAL");
  const files = S.files;
  return `
  <header class="site-nav">
    <div class="brand" data-act="home"><div class="logo">${I("compass", 20)}</div><div><b>KYCompass</b><span>Requirements intelligence for KYC</span></div></div>
    <div class="spacer"></div>
    ${S.projects.length ? `<button class="btn ghost" data-act="scroll-to" data-target="recent">Your projects</button>` : ""}
    <button class="btn ghost icon-only" data-act="theme" aria-label="Toggle theme">${I("moon", 17)}</button>
  </header>
  <section class="hero">
    <div class="eyebrow">${I("shield", 14)} Agentic requirements engineering for KYC and customer onboarding</div>
    <h1>Turn vague stakeholder notes into a <em>compliant, traceable</em> requirements spec.</h1>
    <p class="lede">Paste an interview, drop in an email or a policy document. KYCompass extracts the requirements, checks them against KYC / AML / data-protection rules, scores the risks, asks you the questions that matter (answer only the ones you choose) and recommends the right SDLC.</p>
    <div class="card start-card"><div class="card-b stack">
      <div class="grid g2">
        <div class="field"><label for="start-name">Project name</label><input id="start-name" class="input" data-draft="start-name" value="${esc(draft("start-name", ""))}" placeholder="e.g. Mobile account opening"></div>
        <div class="field"><label>Rules that apply</label><div class="row">${juris.map(([k, v]) => `<button class="chip" aria-pressed="${S.jurisdictions.includes(k)}" data-act="toggle-juris" data-k="${k}">${esc(v)}</button>`).join("")}</div></div>
      </div>
      <div class="row between"><div class="seg" role="tablist"><button role="tab" aria-selected="${S.startMode === "paste"}" data-act="start-mode" data-v="paste">Paste text</button><button role="tab" aria-selected="${S.startMode === "upload"}" data-act="start-mode" data-v="upload">Upload files</button></div>
        ${S.startMode === "paste" ? `<button class="linkbtn sm" data-act="fill-example">Fill in an example</button>` : ""}</div>
      ${S.startMode === "paste"
        ? `<textarea id="start-text" class="input" style="min-height:190px" data-draft="start-text" placeholder="Paste interview notes, an email thread, meeting minutes or a policy extract. Vague or incomplete is fine, that is what the questions are for.">${esc(draft("start-text"))}</textarea>`
        : dropzone("start")}
      <div class="row between"><span class="xs muted">${I("lock", 12)} Identifiers (PAN, Aadhaar, cards, phone, email) are masked before analysis. <kbd>Ctrl</kbd> + <kbd>Enter</kbd> to start.</span>
        <button class="btn primary lg" data-act="start-analyse" ${S.busy ? "disabled" : ""}>${I("spark", 17)}${S.busy ? "Starting..." : "Analyse requirements"}</button></div>
    </div></div>
  </section>
  <section class="steps">
    ${[["Add what you have", "Notes, emails, transcripts, policies. Vague input is expected."], ["Agents analyse it", "Extract, classify, map to regulations, find conflicts and gaps, score risk."], ["You choose what to clarify", "Weak requirements get optional questions. Answer some, skip others."], ["Get the deliverables", "SRS, user stories, traceability matrix, risk register and a justified SDLC."]]
      .map(([t, p], i) => `<div class="step-card"><div class="num">${i + 1}</div><h3>${t}</h3><p>${p}</p></div>`).join("")}
  </section>
  ${S.samples.length ? `<section class="section"><h2>Try a sample</h2><p>Three ready-made scenarios. Open an analysed demo instantly, or run the analysis live. The vague one shows clarification questions and a Spiral recommendation; the other two show how the SDLC recommendation changes.</p>
    <div class="grid g3">${S.samples.map((s) => `<div class="card sample"><h3>${esc(s.name)}</h3><p>${esc(s.description)}</p><div class="row between"><span class="xs muted">${plural(s.inputs, "input")}</span><span class="row">${S.demos.some((d) => d.id === s.id) ? `<button class="btn sm primary" data-act="open-demo" data-id="${esc(s.id)}">${I("arrow", 14)}Open analysed demo</button>` : ""}<button class="btn sm ${S.demos.some((d) => d.id === s.id) ? "" : "primary"}" data-act="start-sample" data-id="${esc(s.id)}">Analyse live</button></span></div>${(() => { const dm = S.demos.find((d) => d.id === s.id); return dm ? `<div class="xs muted">Demo: ${dm.requirements} requirements, ${dm.questions} questions, recommends <b>${esc(dm.sdlc || "-")}</b>. Opens instantly with no model calls.</div>` : ""; })()}</div>`).join("")}</div></section>` : ""}
  ${S.projects.length ? `<section class="section" id="recent"><h2>Your projects</h2><p>Everything is stored locally. Open a project to continue.</p>
    <div class="card list">${S.projects.map((p) => `<div class="list-item"><div style="flex:1;min-width:0"><b>${esc(p.name)}</b><div class="xs muted">${plural(p.requirements, "requirement")}, ${p.approved} approved · ${plural(p.documents, "input")}${p.sdlc ? ` · ${esc(p.sdlc)}` : ""} · ${esc(fmtTime(p.updated_at))}</div></div>
      ${p.running ? pill("analysing", "accent") : ""}<button class="btn sm" data-act="open-project" data-id="${p.id}">Open</button><button class="btn sm ghost icon-only danger" data-act="delete-project" data-id="${p.id}" aria-label="Delete project">${I("trash", 15)}</button></div>`).join("")}</div></section>` : ""}
  <footer class="site">KYCompass is advisory. Regulatory mappings are proposals for a compliance officer, never legal determinations. Knowledge-base text is paraphrased for prototyping: verify it against official sources. ${h.kb ? `KB ${esc(h.kb.version)} · ${h.kb.clauses} clauses · ${esc(h.model)}` : ""}</footer>`;
};

function dropzone(scope) {
  const files = K.S.files;
  return `<div>
    <div class="drop" id="drop-${scope}" data-act="pick-files" tabindex="0">${I("upload", 26)}<div><b>Drop files here</b> or click to browse</div><div class="xs muted">.txt .md .eml .docx .pdf · up to 8 MB each</div></div>
    <input type="file" id="file-input" multiple accept=".txt,.md,.eml,.docx,.pdf,.csv,.json" class="hidden">
    ${files.length ? `<div class="list card" style="margin-top:10px">${files.map((f, i) => `<div class="list-item" style="padding:8px 14px;align-items:center">${I("file", 16)}<span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(f.name)}</span><span class="xs muted">${Math.max(1, Math.round(f.size / 1024))} KB</span><button class="btn sm ghost icon-only" data-act="remove-file" data-i="${i}" aria-label="Remove file">${I("x", 14)}</button></div>`).join("")}</div>` : ""}
  </div>`;
}

/* ================================================================== overview */
K.PAGES.Overview = () => {
  const d = D(), m = d.validation?.metrics || {}, reqs = live();
  const unanalysed = d.documents.filter((x) => !x.analysed).length;
  const head = pageHead(d.project.name, esc(d.project.description || "Stakeholder inputs, analysed requirements and approvals for this project."),
    `${runButton(d, unanalysed)}<button class="btn" data-go="Export">${I("download", 15)}Export</button>`);
  if (!d.requirements.length) {
    const body = !d.documents.length
      ? empty("file", "Add your first input", "Paste stakeholder notes or upload documents. Vague and incomplete is fine.", `<button class="btn primary" data-go="Inputs">${I("plus", 15)}Add input</button>`)
      : empty("spark", d.job?.status === "running" ? "Analysis is running" : "Ready to analyse", d.job?.status === "running" ? "Watch the progress panel at the bottom right." : `${plural(d.documents.length, "input")} added. Run the agents to extract and check the requirements.`, d.job?.status === "running" ? "" : `<button class="btn primary" data-act="analyse">${I("spark", 15)}Analyse</button>`);
    return head + `<div class="card">${body}</div>`;
  }
  const by = (s) => d.requirements.filter((r) => r.approval_status === s);
  const stat = (l, v, s = "") => `<div class="card stat"><div class="l">${l}</div><div class="v">${v}</div><div class="s">${s}</div></div>`;
  const cats = Object.entries(reqs.reduce((a, r) => (r.categories.forEach((c) => (a[c] = (a[c] || 0) + 1)), a), {})).sort((a, b) => b[1] - a[1]);
  const cmax = Math.max(1, ...cats.map((c) => c[1]));
  const g = d.guard || {};
  const list = (items, empt) => items.length ? items.slice(0, 6).map((r) => `<div class="list-item" style="padding:9px 18px;cursor:pointer" data-act="open-req" data-id="${r.id}"><span class="mono xs muted" style="min-width:84px">${esc(r.ref)}</span><span class="sm clamp" style="flex:1">${esc(r.statement)}</span>${openQs().filter((q) => q.requirement_id === r.id).length ? pill(`${openQs().filter((q) => q.requirement_id === r.id).length} open q`, "warn") : ""}</div>`).join("") + (items.length > 6 ? `<div class="list-item sm muted" style="padding:9px 18px">+ ${items.length - 6} more</div>` : "") : `<div class="list-item muted sm" style="padding:14px 18px">${empt}</div>`;
  return head + `
  <div class="grid g4" style="margin-bottom:16px">
    ${stat("Requirements", reqs.length, `${reqs.filter((r) => r.origin === "stated").length} stated · ${reqs.filter((r) => r.origin === "derived").length} derived by the system`)}
    ${stat("Need clarification", reqs.filter((r) => r.is_weak).length, `${plural(openQs().length, "question")} open`)}
    ${stat("Control coverage", d.validation ? `${Math.round(m.control_coverage_pct || 0)}%` : "-", d.validation ? `${m.controls_partial || 0} partial · ${m.controls_gap || 0} gaps` : "Not computed yet")}
    ${stat("Avg confidence", d.validation ? pct(m.avg_confidence) : "-", d.validation ? (m.baseline_ready ? "Baseline ready" : "Baseline blocked") : "Not computed yet")}
  </div>
  <div class="grid g-side">
    <div class="stack">
      <div class="card"><div class="card-h"><div><h2>Next steps</h2><p>What to do now to move this project forward</p></div></div><div class="list">${nextSteps(d).map((s) => `<div class="list-item"><span class="dot ${s.tone}" style="margin-top:7px"></span><div style="flex:1"><b>${esc(s.title)}</b><div class="sm muted">${esc(s.text)}</div></div>${s.btn}</div>`).join("")}</div></div>
      <div class="card"><div class="card-h"><div><h2>Review status</h2><p>Approved versus still needing attention</p></div><button class="btn sm" data-go="Requirements">All requirements</button></div>
        <div class="grid g2" style="gap:0"><div style="border-right:1px solid var(--border)"><div class="list-item" style="padding-bottom:4px">${pill(`Approved ${by("approved").length}`, "ok")}</div>${list(by("approved"), "Nothing approved yet.")}</div>
        <div><div class="list-item" style="padding-bottom:4px">${pill(`Needs revision ${by("needs_revision").length}`, "warn")} ${pill(`Pending ${by("pending").length}`)}</div>${list([...by("needs_revision"), ...by("pending")], "Everything is decided.")}</div></div></div>
      <div class="card"><div class="card-h"><div><h2>Baseline readiness</h2><p>${(d.validation?.gates || []).filter((x) => x.passed).length} of ${(d.validation?.gates || []).length} quality gates passing</p></div>${m.baseline_ready ? pill("Ready", "ok") : pill("Blocked", "warn")}</div>
        <div class="list">${(d.validation?.gates || []).map((x) => `<div class="list-item" style="padding:10px 18px;align-items:center"><span class="dot ${x.passed ? "ok" : "warn"}"></span><div style="flex:1"><div>${esc(x.title)}</div><div class="xs muted">${esc(x.detail)}</div></div></div>`).join("")}</div></div>
    </div>
    <div class="stack">
      <div class="card"><div class="card-h"><h2>By status</h2></div><div class="card-b stack" style="gap:10px">${["approved", "needs_revision", "pending", "rejected"].map((s) => `<div><div class="row between sm"><span>${cap(s)}</span><span class="muted">${by(s).length}</span></div><div class="bar ${s === "approved" ? "ok" : s === "rejected" ? "bad" : s === "needs_revision" ? "warn" : ""}" style="margin-top:4px"><span style="width:${(by(s).length / Math.max(1, d.requirements.length)) * 100}%"></span></div></div>`).join("")}</div></div>
      <div class="card"><div class="card-h"><div><h2>By category</h2><p>Multi-label: a requirement can sit in several</p></div></div><div class="card-b stack" style="gap:9px">${cats.map(([k, n]) => `<button class="linkbtn" data-act="filter-cat" data-cat="${esc(k)}" style="color:inherit;font-weight:500;text-align:left"><div class="row between sm"><span>${esc(cap(k))}</span><span class="muted">${n}</span></div><div class="bar" style="margin-top:3px;height:6px"><span style="width:${(n / cmax) * 100}%"></span></div></button>`).join("")}</div></div>
      <div class="card"><div class="card-h"><div><h2>Trust and safety</h2><p>Guards applied to this analysis</p></div>${I("shield", 18)}</div><div class="card-b"><dl class="kv">
        <dt>PII values masked</dt><dd>${g.pii_masked || 0}</dd><dt>Injection text quarantined</dt><dd>${g.injection_quarantined || 0}</dd>
        <dt>Ungrounded requirements dropped</dt><dd>${g.ungrounded_requirements || 0}</dd><dt>Invalid citations dropped</dt><dd>${g.invalid_citations || 0}</dd>
        <dt>Mappings needing legal review</dt><dd>${m.needs_legal_review || 0}</dd><dt>Knowledge base</dt><dd>${esc(K.S.health?.kb?.version || "")}</dd><dt>Model</dt><dd>${esc(K.S.health?.model || "")}</dd></dl></div></div>
      ${d.last_run ? `<div class="card"><div class="card-h"><div><h2>Last run</h2><p>${esc(cap(d.last_run.kind || "analysis"))} · ${esc(fmtTime(d.last_run.at))}</p></div>${I("clock", 17)}</div><div class="card-b"><dl class="kv"><dt>Duration</dt><dd>${fmtDur(d.last_run.seconds || 0)}</dd><dt>Model calls</dt><dd>${d.last_run.llm_calls ?? "-"}</dd></dl></div></div>` : ""}
    </div>
  </div>`;
};

function runButton(d, unanalysed) {
  if (isBusy()) return "";
  if (unanalysed) return `<button class="btn primary" data-act="analyse">${I("spark", 15)}Analyse ${plural(unanalysed, "new input")}</button>`;
  if (!d.last_run) return `<button class="btn primary" data-act="analyse">${I("refresh", 15)}Resume analysis</button>`;
  return `<button class="btn" data-act="analyse" title="Only re-checks what changed, so it is quick">${I("refresh", 15)}Re-run analysis</button>`;
}

function nextSteps(d) {
  const steps = [], m = d.validation?.metrics || {};
  const unanalysed = d.documents.filter((x) => !x.analysed).length;
  const btn = (label, attr, primary = false) => `<button class="btn sm ${primary ? "primary" : ""}" ${attr}>${label}</button>`;
  if (isBusy()) steps.push({ tone: "run", title: "Analysis in progress", text: "Results appear here as each stage finishes.", btn: "" });
  else if (!d.last_run && !unanalysed) steps.push({ tone: "warn", title: "The last analysis did not finish", text: "Finished stages are saved. Resume to continue where it stopped.", btn: btn("Resume", 'data-act="analyse"', true) });
  else if (unanalysed) steps.push({ tone: "warn", title: `${plural(unanalysed, "input")} not analysed yet`, text: "Run the agents so new input becomes requirements.", btn: btn("Analyse", 'data-act="analyse"', true) });
  if (unappliedAnswers().length && !isBusy()) steps.push({ tone: "warn", title: `${plural(unappliedAnswers().length, "answer")} ready to apply`, text: "Fold your answers into the requirements and re-check them.", btn: btn("Apply and re-analyse", 'data-act="apply-answers"', true) });
  if (openQs().length) steps.push({ tone: "warn", title: `${plural(openQs().length, "clarification question")} open`, text: "Answer the ones you can; skip the rest. Skipped ones stay listed as open issues.", btn: btn("Open questions", 'data-go="Clarifications"') });
  if (m.open_conflicts) steps.push({ tone: "bad", title: `${plural(m.open_conflicts, "conflict")} between requirements`, text: "Decide how contradictory or duplicate requirements are resolved.", btn: btn("Resolve", 'data-go="Conflicts"') });
  const undecided = d.requirements.filter((r) => ["pending", "needs_revision"].includes(r.approval_status)).length;
  if (undecided) steps.push({ tone: "", title: `${plural(undecided, "requirement")} waiting for a decision`, text: "Approve, send back for revision or reject each one.", btn: btn("Review", 'data-go="Requirements"') });
  const gates = Object.entries(d.gates).filter(([, g]) => g.status !== "approved");
  if (gates.length && d.requirements.length) steps.push({ tone: "", title: `${plural(gates.length, "approval gate")} still open`, text: gates.map(([, g]) => g.title).join(", "), btn: btn("Approvals", 'data-go="Approvals"') });
  if (!steps.length) steps.push({ tone: "ok", title: "Everything is in order", text: "All inputs analysed, questions handled and gates signed off.", btn: btn("Export deliverables", 'data-go="Export"', true) });
  return steps;
}

/* ===================================================================== inputs */
K.PAGES.Inputs = () => {
  const d = D(), S = K.S, files = S.files;
  const unanalysed = d.documents.filter((x) => !x.analysed).length;
  const types = (S.health?.source_types || ["notes"]);
  return pageHead("Inputs", "Everything stakeholders told you: interviews, emails, meeting notes, policies, audit findings. Text is masked on arrival and only the masked version is stored.",
    unanalysed && !isBusy() ? `<button class="btn primary" data-act="analyse">${I("spark", 15)}Analyse ${plural(unanalysed, "new input")}</button>` : "") + `
  <div class="card" style="margin-bottom:16px"><div class="card-h"><div><h2>Add input</h2><p>Paste text or upload files. You can add more at any time.</p></div>
    <div class="seg"><button aria-selected="${S.inputMode === "paste"}" data-act="input-mode" data-v="paste">Paste</button><button aria-selected="${S.inputMode === "upload"}" data-act="input-mode" data-v="upload">Upload</button></div></div>
    <div class="card-b stack">
      <div class="grid g3">
        <div class="field"><label>Title</label><input class="input" data-draft="in-title" value="${esc(draft("in-title"))}" placeholder="e.g. Compliance email, 12 March"></div>
        <div class="field"><label>Source type</label><select class="input" data-draft="in-type">${types.map((t) => `<option ${draft("in-type", "notes") === t ? "selected" : ""}>${esc(t)}</option>`).join("")}</select></div>
        <div class="field"><label>Speaker role (optional)</label><input class="input" data-draft="in-role" value="${esc(draft("in-role"))}" placeholder="e.g. Compliance officer"></div>
      </div>
      ${S.inputMode === "paste"
        ? `<textarea class="input" style="min-height:150px" data-draft="in-text" placeholder="Paste text here...">${esc(draft("in-text"))}</textarea>` : dropzone("inputs")}
    </div>
    <div class="card-f"><button class="btn" data-act="add-input" data-run="0">Add without analysing</button><button class="btn primary" data-act="add-input" data-run="1">${I("spark", 15)}Add and analyse</button></div></div>
  <div class="card"><div class="card-h"><div><h2>Sources · ${d.documents.length}</h2><p>One row per document. Raw text is never stored.</p></div></div>
    ${d.documents.length ? `<div class="list">${d.documents.map((x) => `<div class="list-item">${I("file", 18)}<div style="flex:1;min-width:0"><div class="row"><b>${esc(x.title)}</b>${x.analysed ? pill("analysed", "ok") : pill("not analysed", "warn")}</div>
      <div class="xs muted">${esc(x.source_type)}${x.role ? " · " + esc(x.role) : ""} · ${plural(x.words, "word")}</div>
      <div class="row" style="margin-top:6px">${Object.entries(x.pii_found || {}).map(([k, v]) => `<span class="pill info" title="Replaced by a placeholder before storage">${I("lock", 11)} ${v} ${esc(cap(k))} masked</span>`).join("")}${(x.injection || []).length ? `<span class="pill bad" title="${esc(x.injection.map((i) => i.snippet).join(" | "))}">${I("alert", 11)} ${x.injection.length} injection attempt(s) quarantined</span>` : ""}</div></div>
      <button class="btn sm" data-act="view-doc" data-id="${x.id}">${I("eye", 14)}View masked text</button>${x.analysed ? "" : `<button class="btn sm ghost icon-only danger" data-act="remove-doc" data-id="${x.id}" aria-label="Remove">${I("trash", 15)}</button>`}</div>`).join("")}</div>` : empty("file", "No inputs yet", "Add text or files above.")}</div>`;
};

/* ================================================================ requirements */
function filteredReqs() {
  const f = K.S.f, q = f.rqSearch.trim().toLowerCase();
  return D().requirements.filter((r) =>
    (f.rqStatus === "all" || r.approval_status === f.rqStatus) && (!f.rqCat || r.categories.includes(f.rqCat)) && (!f.rqWeak || r.is_weak) &&
    (f.rqOrigin === "all" || r.origin === f.rqOrigin) && (!q || `${r.ref} ${r.statement} ${r.source_stakeholder}`.toLowerCase().includes(q)));
}

K.PAGES.Requirements = () => {
  const d = D(), f = K.S.f;
  if (!d.requirements.length) return pageHead("Requirements") + `<div class="card">${empty("list", "No requirements yet", "Add stakeholder input and run the analysis. Extracted and derived requirements appear here.", `<button class="btn primary" data-go="Inputs">${I("plus", 15)}Add input</button>`)}</div>`;
  const cnt = (s) => d.requirements.filter((r) => r.approval_status === s).length;
  const cats = Object.entries(d.requirements.reduce((a, r) => (r.categories.forEach((c) => (a[c] = (a[c] || 0) + 1)), a), {})).sort((a, b) => b[1] - a[1]);
  const rows = filteredReqs();
  return pageHead("Requirements", "Extracted from the inputs, plus requirements the system derived from mandatory controls and security analysis. Open one to see its evidence, regulations and risk.",
    `<button class="btn" data-go="Export">${I("download", 15)}Export</button>`) + `
  <div class="stack" style="gap:12px;margin-bottom:14px">
    <div class="row"><div style="position:relative;flex:1;min-width:220px;max-width:360px"><span style="position:absolute;left:11px;top:9px;color:var(--text-3)">${I("search", 16)}</span><input class="input" style="padding-left:34px" id="rq-search" placeholder="Search requirements" value="${esc(f.rqSearch)}"></div>
      <div class="seg">${[["all", "All", d.requirements.length], ["pending", "Pending", cnt("pending")], ["needs_revision", "Needs revision", cnt("needs_revision")], ["approved", "Approved", cnt("approved")], ["rejected", "Rejected", cnt("rejected")]].map(([v, l, n]) => `<button aria-selected="${f.rqStatus === v}" data-act="rq-status" data-v="${v}">${l}<span class="n">${n}</span></button>`).join("")}</div>
      <div class="seg">${[["all", "Any origin"], ["stated", "Stated"], ["derived", "Derived"]].map(([v, l]) => `<button aria-selected="${f.rqOrigin === v}" data-act="rq-origin" data-v="${v}">${l}</button>`).join("")}</div>
      <button class="chip" aria-pressed="${f.rqWeak}" data-act="rq-weak">${I("help", 13)} Weak only</button></div>
    <div class="row"><button class="chip" aria-pressed="${!f.rqCat}" data-act="rq-cat" data-v="">All categories</button>${cats.map(([k, n]) => `<button class="chip" aria-pressed="${f.rqCat === k}" data-act="rq-cat" data-v="${esc(k)}">${esc(cap(k))}<span class="n">${n}</span></button>`).join("")}</div>
  </div>
  <div class="card">${rows.length ? `<div class="list">${rows.map(reqRow).join("")}</div>` : empty("search", "No matching requirements", "Try a different search or clear the filters.", `<button class="btn sm" data-act="rq-reset">Clear filters</button>`)}</div>`;
};

function reqRow(r) {
  const oq = openQs().filter((q) => q.requirement_id === r.id).length;
  return `<div class="req" data-act="open-req" data-id="${r.id}"><div class="ref">${esc(r.ref)}</div><div class="body"><div class="statement clamp">${esc(r.statement)}</div>
    <div class="meta">${statusPill(r.approval_status)}${r.risk_level ? riskPill(r.risk_level) : ""}${pill(cap(r.priority))}${r.is_weak ? pill("weak", "warn") : ""}${oq ? pill(`${oq} open question${oq > 1 ? "s" : ""}`, "warn") : ""}${r.origin === "derived" ? pill("derived", "info") : ""}
    ${r.regulations.length ? `<span class="pill accent">${I("scale", 11)} ${r.regulations.length} regulation${r.regulations.length > 1 ? "s" : ""}</span>` : ""}
    ${r.categories.slice(0, 3).map((c) => `<span class="tag">${esc(cap(c))}</span>`).join("")}${confBar(r.confidence_score)}</div></div></div>`;
}

/* ---------------------------------------------------------------------- drawer */
function drawerHtml(r) {
  const d = D(), qs = questionsOf(r.id), risk = d.risks.find((x) => x.requirement_id === r.id);
  const S = K.S, role = S.identity.role;
  const sec = (t, body) => (body ? `<section><h3>${t}</h3>${body}</section>` : "");
  const sensitive = (r.risk_level === "high" && r.categories.some((c) => ["security", "privacy", "regulatory"].includes(c))) || r.regulations.some((m) => m.needs_legal_review);
  const canDecide = !sensitive || ["security", "compliance", "architect"].includes(role);
  const dep = (r.dependencies || []).map(reqTag).join(" ");
  return `<div class="scrim" data-act="close-drawer"></div><aside class="drawer" role="dialog" aria-label="Requirement ${esc(r.ref)}">
    <div class="drawer-h"><div><div class="mono sm muted">${esc(r.ref)}</div><div class="row" style="margin-top:6px">${statusPill(r.approval_status)}${riskPill(r.risk_level)}${pill(cap(r.priority))}${r.origin === "derived" ? pill("derived by system", "info") : ""}${r.is_weak ? pill("weak", "warn") : ""}</div></div>
      <button class="btn sm icon-only ghost" data-act="close-drawer" aria-label="Close">${I("x", 18)}</button></div>
    <div class="drawer-b">
      <section>${S.editing
        ? `<h3>Edit statement</h3><textarea class="input" id="edit-statement" style="min-height:110px">${esc(draft("edit-" + r.id, r.statement))}</textarea><div class="hint xs muted" style="margin-top:6px">Saving resets this requirement to pending and re-checks it on the next analysis.</div>`
        : `<p class="statement">${esc(r.statement)}</p><div style="margin-top:10px">${tags(r.categories)}</div>`}</section>
      ${r.is_weak || qs.length ? sec("Quality", `${r.quality_flags.map((q) => `<div class="callout warn" style="margin-bottom:6px">${I("help", 15)}<div><b>${esc(cap(q.kind))}.</b> ${esc(q.detail)}</div></div>`).join("")}${qs.map((q) => qCard(q, true)).join("")}`) : ""}
      ${sec("Evidence", `${r.source_excerpt ? `<div class="quote">"${esc(r.source_excerpt)}"</div>` : ""}<div class="sm muted" style="margin-top:8px">${esc(r.source_stakeholder)}${r.source_document ? " · " + esc(r.source_document) : ""}</div>${r.origin === "derived" ? `<div class="callout info" style="margin-top:8px">${I("info", 15)}<div>${esc(r.derived_reason.replace(/^\[C-[A-Z-]+\]\s*/, ""))}</div></div>` : ""}`)}
      ${sec("Business justification", r.business_justification ? `<p>${esc(r.business_justification)}</p>` : "")}
      ${sec("Assumptions", r.assumptions.length ? `<ul class="ac">${r.assumptions.map((a) => `<li>${esc(a)}</li>`).join("")}</ul>` : "")}
      ${sec("Acceptance criteria", r.acceptance_criteria.length ? `<ul class="ac">${r.acceptance_criteria.map((a) => `<li>${esc(a)}</li>`).join("")}</ul>` : "")}
      ${sec("Regulations", r.regulations.length ? r.regulations.map((m) => `<div class="card" style="padding:11px 14px;margin-bottom:8px"><div class="row between"><b class="sm">${esc(m.citation)}</b><span class="row" style="gap:6px">${pill(m.jurisdiction)}${m.needs_legal_review ? pill("needs legal review", "warn") : ""}</span></div>
        <div class="sm muted" style="margin:4px 0 6px">${esc(m.rationale)}</div>${confBar(m.confidence)}</div>`).join("") + `<div class="xs muted">Proposed for a compliance officer. Not a legal determination.</div>` : `<p class="sm muted">No regulation maps to this requirement.</p>`)}
      ${sec("Risk", risk ? `<div class="row" style="margin-bottom:6px">${riskPill(r.risk_level)}${pill(`Likelihood ${risk.likelihood}`)}${pill(`Impact ${risk.impact}`)}${pill(cap(risk.risk_type), "info")}</div><p>${esc(risk.risk)}</p><p class="sm muted" style="margin-top:6px"><b>Mitigation:</b> ${esc(risk.mitigation)}</p>` : "")}
      ${sec("Confidence", `<div class="row">${confBar(r.confidence_score)}<span class="xs muted">model confidence, clarity and regulatory support combined</span></div>`)}
      ${sec("Depends on", dep)}
      ${sec("History", r.history.length ? `<ul class="ac">${r.history.map((h) => `<li class="sm">${esc(cap((h.action || "").replace(":", " ")))}${h.by ? ` by ${esc(h.by)}` : ""}${h.at ? ` <span class="muted">${esc(fmtTime(h.at))}</span>` : ""}${h.note ? ` · ${esc(h.note)}` : ""}</li>`).join("")}</ul>` : "")}
      ${!canDecide ? `<div class="callout warn">${I("lock", 15)}<div>This requirement is high-risk or needs legal review, so a <b>security officer, compliance officer or architect</b> must decide it. You are acting as <b>${esc(roleName(role))}</b>. Change role at the top right.</div></div>` : ""}
    </div>
    <div class="drawer-f">${S.editing
      ? `<button class="btn" data-act="cancel-edit">Cancel</button><button class="btn primary" data-act="save-edit" data-id="${r.id}">${I("check", 15)}Save change</button>`
      : `<button class="btn ghost" data-act="start-edit">${I("edit", 14)}Edit</button><span style="flex:1"></span>
         <button class="btn danger" data-act="decide" data-id="${r.id}" data-d="rejected">Reject</button>
         <button class="btn" data-act="decide" data-id="${r.id}" data-d="needs_revision">Send back for revision</button>
         <button class="btn primary" data-act="decide" data-id="${r.id}" data-d="approved">${I("check", 15)}Approve</button>`}</div></aside>`;
}

/* ================================================================ clarifications */
function qCard(q, compact = false) {
  const r = reqById(q.requirement_id);
  const key = "q-" + q.id;
  const done = q.status !== "open";
  const body = q.status === "open"
    ? `${q.options.length ? `<div class="opts">${q.options.map((o) => `<button class="chip" data-act="pick-option" data-q="${q.id}" data-v="${esc(o)}">${esc(o)}</button>`).join("")}</div>` : ""}
       <textarea class="input" style="min-height:62px" data-draft="${key}" placeholder="Your answer (optional)...">${esc(draft(key))}</textarea>
       <div class="row end"><button class="btn sm ghost" data-act="skip-q" data-q="${q.id}">Skip this question</button><button class="btn sm primary" data-act="answer-q" data-q="${q.id}">Save answer</button></div>`
    : q.status === "answered"
      ? `<div class="callout ok">${I("check", 15)}<div><b>Your answer:</b> ${esc(q.answer)}<div class="xs muted" style="margin-top:3px">${q.applied ? "Folded into the requirement." : "Saved. Apply it to update the requirement."}</div></div></div>${q.applied ? "" : `<div class="row end"><button class="btn sm ghost" data-act="reopen-q" data-q="${q.id}">Change answer</button></div>`}`
      : `<div class="callout">${I("info", 15)}<div>Skipped. This stays in the SRS as an open issue.</div></div><div class="row end"><button class="btn sm" data-act="reopen-q" data-q="${q.id}">Answer it after all</button></div>`;
  return `<div class="${compact ? "" : "card"} qcard ${done ? "done" : ""}" ${compact ? 'style="border:1px solid var(--border);border-radius:10px;margin-bottom:8px"' : ""}>
    ${!compact && r ? `<div class="row"><button class="tag mono" data-act="open-req" data-id="${r.id}">${esc(r.ref)}</button><span class="sm muted clamp" style="flex:1">${esc(r.statement)}</span></div>` : ""}
    <div><b>${esc(q.question)}</b>${q.why ? `<div class="xs muted" style="margin-top:2px">Why we ask: ${esc(q.why)}</div>` : ""}</div>${body}</div>`;
}

K.PAGES.Clarifications = () => {
  const d = D(), f = K.S.f;
  const all = d.questions;
  const c = { open: all.filter((q) => q.status === "open").length, answered: all.filter((q) => q.status === "answered").length, skipped: all.filter((q) => q.status === "skipped").length };
  const head = pageHead("Clarifications", "Weak or vague requirements get questions a business analyst would ask. <b>Answering is optional.</b> Answer what you know, skip the rest. Answers are folded back into the requirement and re-checked.",
    `<button class="btn primary" data-act="apply-answers" ${unappliedAnswers().length && !isBusy() ? "" : "disabled"}>${I("refresh", 15)}Apply ${unappliedAnswers().length || ""} answer${unappliedAnswers().length === 1 ? "" : "s"} and re-analyse</button>`);
  if (!all.length) return head + `<div class="card">${empty("chat", "No questions", d.requirements.length ? "Every requirement is clear enough to build against. Nothing to clarify." : "Run an analysis first. Weak requirements will get questions here.")}</div>`;
  const rows = all.filter((q) => f.qStatus === "all" || q.status === f.qStatus);
  const groups = {};
  rows.forEach((q) => (groups[q.requirement_id] ||= []).push(q));
  return head + `<div class="callout info" style="margin-bottom:14px">${I("info", 16)}<div><b>You are in control.</b> A question is a suggestion, not a blocker. Skipped questions are listed as open issues in the SRS instead of holding up the baseline.</div></div>
  <div class="row between" style="margin-bottom:14px"><div class="seg">${[["open", "Open", c.open], ["answered", "Answered", c.answered], ["skipped", "Skipped", c.skipped], ["all", "All", all.length]].map(([v, l, n]) => `<button aria-selected="${f.qStatus === v}" data-act="q-status" data-v="${v}">${l}<span class="n">${n}</span></button>`).join("")}</div>
    ${c.open ? `<button class="btn sm" data-act="skip-all">Skip all open questions</button>` : ""}</div>
  ${rows.length ? `<div class="stack">${Object.values(groups).flat().map((q) => qCard(q)).join("")}</div>` : `<div class="card">${empty("check", "Nothing here", f.qStatus === "open" ? "No open questions. Nice." : "No questions with this status.")}</div>`}`;
};
