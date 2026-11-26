/* Pages part 2: conflicts, compliance, risks, SDLC, approvals, audit, export. */
"use strict";

/* =================================================================== conflicts */
K.PAGES.Conflicts = () => {
  const d = D();
  const head = pageHead("Conflicts", "Contradictions and duplicates between requirements, often from different stakeholders. Record how each is resolved; this feeds the conflict-resolution approval gate.");
  if (!d.requirements.length) return head + `<div class="card">${empty("alert", "Nothing analysed yet", "Run an analysis first.")}</div>`;
  if (!d.conflicts.length) return head + `<div class="card">${empty("check", "No conflicts found", "No contradictory or duplicate requirements were detected.")}</div>`;
  return head + `<div class="stack">${d.conflicts.map((c) => {
    const reqs = c.requirement_ids.map((id) => reqById(id)).filter(Boolean);
    const key = "cf-" + c.id;
    return `<div class="card"><div class="card-h"><div class="row">${pill(cap(c.kind), c.kind === "contradiction" ? "bad" : "warn")}${c.status === "resolved" ? pill("resolved", "ok") : pill("open", "warn")}<span class="xs muted">confidence ${pct(c.confidence)}</span></div></div>
      <div class="card-b stack"><p>${esc(c.explanation)}</p>
        <div class="grid g2" style="gap:10px">${reqs.map((r) => `<button class="card" data-act="open-req" data-id="${r.id}" style="text-align:left;padding:12px 14px;cursor:pointer;background:var(--surface-2)"><div class="row between"><b class="mono xs">${esc(r.ref)}</b><span class="xs muted">${esc(r.source_stakeholder)}</span></div><div class="sm" style="margin-top:4px">${esc(r.statement)}</div></button>`).join("")}</div>
        ${c.status === "resolved" ? `<div class="callout ok">${I("check", 15)}<div><b>Resolution:</b> ${esc(c.resolution)}</div></div>`
          : `<div class="field"><label>How is this resolved?</label><textarea class="input" style="min-height:64px" data-draft="${key}" placeholder="e.g. Keep the 60-second target for low-risk customers and 5 minutes for others, as agreed with the product owner.">${esc(draft(key))}</textarea></div>
             <div class="row end"><button class="btn primary sm" data-act="resolve-conflict" data-id="${c.id}">Record resolution</button></div>`}</div></div>`;
  }).join("")}</div>`;
};

/* =================================================================== compliance */
K.PAGES.Compliance = () => {
  const d = D(), m = d.validation?.metrics || {}, f = K.S.f;
  const head = pageHead("Compliance", "Requirements mapped to KYC / AML / data-protection clauses from the versioned knowledge base, and a check of the mandatory controls. The system proposes mappings; a compliance officer confirms them.",
    `<button class="btn" data-act="open-kb">${I("book", 15)}Browse knowledge base</button><button class="btn" data-go="Approvals">${I("stamp", 15)}Regulatory approval</button>`);
  if (!d.requirements.length) return head + `<div class="card">${empty("scale", "Nothing analysed yet", "Run an analysis first.")}</div>`;
  const st = (s) => d.controls.filter((c) => c.status === s).length;
  const kind = { covered: "ok", partial: "warn", gap: "bad", not_applicable: "" };
  const maps = d.requirements.filter((r) => r.approval_status !== "rejected").flatMap((r) => r.regulations.map((mp) => ({ r, mp }))).filter(({ mp }) => !f.legalOnly || mp.needs_legal_review);
  return head + `
  <div class="grid g4" style="margin-bottom:16px">
    <div class="card stat"><div class="l">Controls covered</div><div class="v">${st("covered")}</div><div class="s">of ${d.controls.length - st("not_applicable")} applicable</div></div>
    <div class="card stat"><div class="l">Partially covered</div><div class="v">${st("partial")}</div><div class="s">add detail to close</div></div>
    <div class="card stat"><div class="l">Gaps</div><div class="v">${st("gap")}</div><div class="s">would be derived as requirements</div></div>
    <div class="card stat"><div class="l">Needs legal review</div><div class="v">${m.needs_legal_review || 0}</div><div class="s">high-impact or low-confidence</div></div>
  </div>
  <div class="card" style="margin-bottom:16px"><div class="card-h"><div><h2>Mandatory control coverage</h2><p>A control is covered when a requirement both cites its regulation and states its substance.</p></div></div>
    <div class="tw"><table><thead><tr><th>Control</th><th>Status</th><th>Regulations</th><th>Covered by</th></tr></thead><tbody>${d.controls.map((c) => `<tr><td><b>${esc(c.title)}</b></td><td>${pill(cap(c.status), kind[c.status])}</td><td class="sm muted">${esc(c.regulations.join("; "))}</td><td>${c.covered_by.length ? `<div class="tags">${c.covered_by.slice(0, 6).map(reqTag).join("")}${c.covered_by.length > 6 ? `<span class="xs muted">+${c.covered_by.length - 6}</span>` : ""}</div>` : '<span class="muted">-</span>'}</td></tr>`).join("")}</tbody></table></div></div>
  <div class="card"><div class="card-h"><div><h2>Requirement to regulation mappings</h2><p>${maps.length} mapping${maps.length === 1 ? "" : "s"} with citations. Only clauses the retriever returned can be cited; others are dropped and counted.</p></div>
    <button class="chip" aria-pressed="${f.legalOnly}" data-act="legal-only">${I("alert", 13)} Needs legal review only</button></div>
    <div class="tw"><table><thead><tr><th>Requirement</th><th>Regulation</th><th>Confidence</th><th>Why</th></tr></thead><tbody>${maps.map(({ r, mp }) => `<tr><td style="min-width:220px">${reqTag(r.ref)}<div class="sm clamp" style="margin-top:4px">${esc(r.statement)}</div></td><td><b class="sm">${esc(mp.citation)}</b><div class="row" style="margin-top:4px;gap:5px">${pill(mp.jurisdiction)}${mp.needs_legal_review ? pill("legal review", "warn") : ""}</div></td><td>${confBar(mp.confidence)}</td><td class="sm muted" style="min-width:220px">${esc(mp.rationale)}</td></tr>`).join("") || `<tr><td colspan="4" class="muted" style="padding:24px;text-align:center">No mappings to show.</td></tr>`}</tbody></table></div></div>`;
};

/* ======================================================================== risks */
K.PAGES.Risks = () => {
  const d = D(), f = K.S.f;
  const head = pageHead("Risks", "Business, technical, compliance, security and operational risks per requirement, scored by likelihood and impact, with mitigations. Below, a STRIDE-style threat model.");
  if (!d.risks.length) return head + `<div class="card">${empty("pulse", "No risk register yet", "Run an analysis to score risks.")}</div>`;
  const cell = {};
  d.risks.forEach((x) => { const k = `${x.likelihood}-${x.impact}`; cell[k] = (cell[k] || 0) + 1; });
  const heat = (l, i) => { const s = l * i; return s >= 20 ? "h5" : s >= 15 ? "h4" : s >= 8 ? "h3" : s >= 4 ? "h2" : "h1"; };
  const list = d.risks.filter((x) => !f.riskCell || `${x.likelihood}-${x.impact}` === f.riskCell).sort((a, b) => b.likelihood * b.impact - a.likelihood * a.impact);
  const lvl = (x) => { const s = x.likelihood * x.impact; return s >= 15 ? "high" : s >= 8 ? "medium" : "low"; };
  const counts = { high: 0, medium: 0, low: 0 };
  d.risks.forEach((x) => counts[lvl(x)]++);
  return head + `
  <div class="grid g-side" style="margin-bottom:16px">
    <div class="card"><div class="card-h"><div><h2>Risk matrix</h2><p>Select a cell to filter the register</p></div>${f.riskCell ? `<button class="btn sm ghost" data-act="risk-clear">Clear filter</button>` : ""}</div><div class="card-b">
      <div class="matrix">${[5, 4, 3, 2, 1].map((l) => `<div class="ax">${l}</div>${[1, 2, 3, 4, 5].map((i) => { const k = `${l}-${i}`, n = cell[k] || 0; return `<button class="${n ? heat(l, i) : "h0"}" data-act="risk-cell" data-k="${k}" aria-pressed="${f.riskCell === k}" ${n ? "" : "disabled"} aria-label="Likelihood ${l}, impact ${i}: ${n} risks">${n || ""}</button>`; }).join("")}`).join("")}<div></div>${[1, 2, 3, 4, 5].map((i) => `<div class="ax">${i}</div>`).join("")}</div>
      <div class="xs muted" style="margin-top:8px;text-align:center">Likelihood (up) · Impact (across)</div></div></div>
    <div class="card"><div class="card-h"><h2>By level</h2></div><div class="card-b stack">${[["high", "bad"], ["medium", "warn"], ["low", "ok"]].map(([k, c]) => `<div><div class="row between sm"><span>${cap(k)}</span><span class="muted">${counts[k]}</span></div><div class="bar ${c}" style="margin-top:4px"><span style="width:${(counts[k] / d.risks.length) * 100}%"></span></div></div>`).join("")}</div></div>
  </div>
  <div class="card" style="margin-bottom:16px"><div class="card-h"><div><h2>Risk register</h2><p>${list.length} of ${d.risks.length} shown</p></div></div><div class="tw"><table><thead><tr><th>Requirement</th><th>Risk</th><th>Type</th><th>L</th><th>I</th><th>Score</th><th>Mitigation</th></tr></thead><tbody>
    ${list.map((x) => { const r = reqById(x.requirement_id); return `<tr><td>${r ? reqTag(r.ref) : ""}</td><td style="min-width:240px">${esc(x.risk)}</td><td>${pill(cap(x.risk_type), "info")}</td><td>${x.likelihood}</td><td>${x.impact}</td><td>${pill(String(x.likelihood * x.impact), { high: "bad", medium: "warn", low: "ok" }[lvl(x)])}</td><td class="sm muted" style="min-width:220px">${esc(x.mitigation)}</td></tr>`; }).join("")}</tbody></table></div></div>
  ${d.threats.length ? `<div class="card"><div class="card-h"><div><h2>Threat model</h2><p>STRIDE-style threats and the requirements that mitigate them</p></div></div><div class="list">${d.threats.map((t) => `<div class="list-item"><div style="flex:1"><div class="row"><b>${esc(t.threat)}</b></div><div class="xs muted">${esc(t.asset)}</div>
    <div class="row" style="margin-top:6px">${t.mitigated_by.length ? t.mitigated_by.map((id) => { const r = reqById(id); return r ? reqTag(r.ref) : ""; }).join("") : pill("no mitigating requirement", "bad")}</div></div>${pill(t.stride, "accent")}</div>`).join("")}</div></div>` : ""}`;
};

/* ======================================================================== SDLC */
K.PAGES.SDLC = () => {
  const d = D(), s = d.sdlc;
  const head = pageHead("SDLC recommendation", "Hard rules and a weighted multi-criteria fit over 14 project factors. Scores are deterministic and explainable; the language model only writes the explanation. The final choice needs the project manager, architect, security and compliance.",
    `<button class="btn" data-go="Approvals">${I("stamp", 15)}Approve SDLC</button>`);
  if (!s) return head + `<div class="card">${empty("flow", "No recommendation yet", "Run an analysis. The SDLC agent scores the project's factors against seven lifecycle models.")}</div>`;
  const top = s.ranking[0], n = s.narrative || {};
  const canChoose = youCan(["project_manager", "architect", "security", "compliance"]);
  return head + `
  <div class="hero-sdlc" style="margin-bottom:16px"><div class="row between"><span class="pill accent">${I("spark", 12)} Recommended</span>${s.chosen !== s.recommended ? pill(`Selected: ${s.chosen}`, "warn") : ""}</div>
    <h2>${esc(s.recommended)} <span class="muted" style="font-size:20px">${Math.round(top.score)}%</span></h2>
    <p style="max-width:880px;color:var(--text-2)">${esc(n.explanation || "")}</p>
    <div class="grid g2" style="margin-top:14px">${n.tradeoffs?.length ? `<div><h4 class="xs muted" style="text-transform:uppercase;letter-spacing:.06em;margin-bottom:4px">Trade-offs</h4><ul class="ac sm">${n.tradeoffs.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>` : ""}${n.would_change_if?.length ? `<div><h4 class="xs muted" style="text-transform:uppercase;letter-spacing:.06em;margin-bottom:4px">This would change if</h4><ul class="ac sm">${n.would_change_if.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>` : ""}</div></div>
  <div class="grid g-side" style="margin-bottom:16px">
    <div class="card"><div class="card-h"><div><h2>Ranked options</h2><p>Suitability across the decision factors</p></div></div><div class="list">${s.ranking.map((o, i) => `<details class="rank-d"><summary style="list-style:none;cursor:pointer"><div class="rank ${i === 0 ? "top" : ""}"><div class="n">${i + 1}</div><div><b>${esc(o.model)}</b>${o.model === s.chosen ? " " + pill("selected", "accent") : ""}<div class="bar" style="margin-top:6px"><span style="width:${o.score}%"></span></div></div><div class="pct">${Math.round(o.score)}%</div></div></summary>
      <div style="padding:0 18px 14px 62px"><ul class="ac sm muted">${o.reasons.map((r) => `<li>${esc(r)}</li>`).join("")}</ul>${o.model !== s.chosen ? `<button class="btn sm" data-act="choose-sdlc" data-m="${esc(o.model)}" ${canChoose ? "" : "disabled title='Project manager, architect, security or compliance only'"}>Use ${esc(o.model)} instead</button>` : ""}</div></details>`).join("")}</div></div>
    <div class="card"><div class="card-h"><div><h2>Decision factors</h2><p>Scored 1 to 5 from the analysed project</p></div></div><div class="list">${s.factors.map((f) => `<div class="list-item" style="padding:10px 18px"><div style="flex:1"><div class="row between sm"><b>${esc(f.label)}</b><span>${f.score}/5</span></div><div class="bar ${f.score >= 4 ? "warn" : ""}" style="margin:5px 0"><span style="width:${f.score * 20}%"></span></div><div class="xs muted">${esc(f.evidence)}</div></div></div>`).join("")}</div></div>
  </div>
  <div class="card"><div class="card-h"><div><h2>Project-specific workflow: ${esc(s.chosen)}</h2><p>${plural(s.workflow.length, "phase")}, each ending in a human approval gate. Customised with this project's open questions, conflicts and control gaps.</p></div></div>
    <div class="card-b"><div class="timeline">${s.workflow.map((p, i) => `<details class="card phase" data-n="${i + 1}" ${i === 0 ? "open" : ""}><summary><div><b>${esc(p.name)}</b><div class="sm muted">${esc(p.goal)}</div></div>${I("chev", 16)}</summary><div class="pb">${[["Activities", p.activities], ["Roles", p.roles], ["Deliverables", p.deliverables], ["Security activities", p.security_activities], ["Testing", p.testing], ["Compliance checkpoints", p.compliance_checkpoints], ["Entry criteria", p.entry_criteria], ["Exit criteria", p.exit_criteria]].filter(([, l]) => l && l.length).map(([t, l]) => `<div><h4>${t}</h4><ul class="ac sm">${l.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>`).join("")}
      <div style="grid-column:1/-1">${pill("Approval gate: " + p.approval_gate, "accent")}</div></div></details>`).join("")}</div></div></div>`;
};

/* ==================================================================== approvals */
K.PAGES.Approvals = () => {
  const d = D(), role = K.S.identity.role, m = d.validation?.metrics || {};
  const head = pageHead("Approvals", "Human sign-off is mandatory for the baseline, regulatory interpretations, conflict resolutions and the SDLC choice. Nothing is approved automatically. Choose your name and role at the top right.");
  if (!d.requirements.length) return head + `<div class="card">${empty("stamp", "Nothing to approve yet", "Run an analysis first.")}</div>`;
  const blocked = (d.validation?.gates || []).filter((x) => !x.passed);
  return head + `<div class="callout info" style="margin-bottom:14px">${I("info", 16)}<div>You are acting as <b>${esc(roleName(role))}</b> (${esc(K.S.identity.user)}). Authentication here is a demo: in production the role must come from the bank's identity provider.</div></div>
  ${blocked.length ? `<div class="callout warn" style="margin-bottom:14px">${I("lock", 16)}<div><b>The baseline cannot be approved yet.</b> First:<ul class="ac" style="margin-top:4px">${blocked.map((x) => `<li>${esc(x.title)}: ${esc(x.detail)}</li>`).join("")}</ul></div></div>` : ""}
  <div class="grid g2">${Object.entries(d.gates).map(([id, g]) => {
    const latest = {}; g.signoffs.forEach((s) => (latest[s.role] = s));
    const mine = g.roles.includes(role);
    const block = id === "baseline" && !m.baseline_ready;
    return `<div class="card gate"><div class="row between"><div><h2>${esc(g.title)}</h2><div class="sm muted" style="margin-top:3px">${esc(g.description)}</div></div>${pill(cap(g.status), { approved: "ok", rejected: "bad", pending: "warn" }[g.status])}</div>
      <div>${g.roles.map((r) => { const s = latest[r]; return `<div class="signoff">${s ? (s.decision === "approved" ? `<span style="color:var(--ok)">${I("check", 16)}</span>` : `<span style="color:var(--bad)">${I("x", 16)}</span>`) : `<span class="dot"></span>`}<span style="flex:1">${esc(roleName(r))}</span><span class="xs muted">${s ? esc(s.user) + " · " + esc(fmtTime(s.at)) : "waiting"}</span></div>`; }).join("")}</div>
      ${g.reset_reason ? `<div class="xs muted">Reset: ${esc(g.reset_reason)}</div>` : ""}
      <div class="row end"><button class="btn sm danger" data-act="signoff" data-g="${id}" data-d="rejected" ${mine ? "" : "disabled"} title="${mine ? "" : "Your role cannot sign this gate"}">Reject</button>
        <button class="btn sm primary" data-act="signoff" data-g="${id}" data-d="approved" ${mine && !block ? "" : "disabled"} title="${!mine ? "Your role cannot sign this gate" : block ? "Blocked until the quality gates pass" : ""}">${I("check", 14)}Approve as ${esc(roleName(role))}</button></div></div>`;
  }).join("")}</div>
  <div class="card" style="margin-top:16px"><div class="card-h"><div><h2>Requirement decisions</h2><p>Each requirement is approved, sent back or rejected individually.</p></div><button class="btn sm" data-go="Requirements">Go to requirements</button></div>
    <div class="card-b row">${["approved", "needs_revision", "pending", "rejected"].map((s) => pill(`${cap(s)} ${d.requirements.filter((r) => r.approval_status === s).length}`, { approved: "ok", needs_revision: "warn", rejected: "bad", pending: "" }[s])).join("")}</div></div>`;
};

/* ======================================================================== audit */
K.PAGES.Audit = () => {
  const a = K.S.audit;
  const head = pageHead("Audit trail", "Every agent action, model call, human decision and generated artefact, hash-chained so any change to a past entry is detectable.",
    `<button class="chip" aria-pressed="${K.S.f.auditLlm}" data-act="audit-llm">Show model calls</button><button class="btn" data-act="reload-audit">${I("refresh", 15)}Refresh</button>`);
  if (!a) return head + `<div class="card"><div class="empty"><div class="spin" style="margin:0 auto 10px"></div>Loading...</div></div>`;
  return head + `<div class="callout ${a.chain_valid ? "ok" : "bad"}" style="margin-bottom:14px">${I(a.chain_valid ? "shield" : "alert", 16)}<div><b>${a.chain_valid ? "Chain verified" : "Chain broken"}.</b> ${a.chain_valid ? `${a.entries_checked} entries checked, every hash links to the one before it.` : `Entry #${a.first_bad_entry} does not match its hash: the log was modified.`}</div></div>
  <div class="card"><div class="tw"><table><thead><tr><th>Time</th><th>Actor</th><th>Action</th><th>Detail</th><th>Hash</th></tr></thead><tbody>${a.entries.map((e) => `<tr><td class="xs muted" style="white-space:nowrap">${esc(fmtTime(e.ts))}</td><td class="sm">${esc(e.actor)}</td><td>${pill(e.action.replace(/_/g, " "), e.action === "llm_call" ? "info" : "")}</td><td class="xs mono" style="max-width:420px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(typeof e.detail === "string" ? e.detail : JSON.stringify(e.detail))}">${esc(typeof e.detail === "string" ? e.detail : JSON.stringify(e.detail)).slice(0, 160)}</td><td class="mono xs muted">${esc(e.hash)}</td></tr>`).join("")}</tbody></table></div></div>`;
};

/* ====================================================================== export */
const FILES = [
  ["SRS.docx", "Software Requirements Specification (Word)", "file", true],
  ["SRS.md", "Software Requirements Specification (Markdown)", "file"],
  ["requirements_report.md", "Requirements report: approved versus still needing revision", "list"],
  ["user_stories.md", "User stories", "chat"],
  ["use_cases.md", "Use cases", "flow"],
  ["requirements_traceability_matrix.csv", "Traceability matrix: statement to source, regulation, story, use case, risk", "grid"],
  ["compliance_control_matrix.csv", "Compliance matrix: requirement to regulation clause", "scale"],
  ["control_coverage.csv", "Mandatory-control coverage", "shield"],
  ["risk_register.csv", "Risk register", "pulse"],
  ["sdlc_workflow.md", "SDLC decision factors and project-specific workflow", "flow"],
  ["assumptions_dependencies_open_issues.md", "Assumptions, dependencies and open issues", "help"],
  ["audit_log.jsonl", "Hash-chained audit log", "lock", true],
  ["project_state.json", "Full project state (machine-readable)", "file", true],
];

K.PAGES.Export = () => {
  const d = D(), pid = K.S.pid, art = d.artefacts;
  const head = pageHead("Export", "Download every deliverable. The SRS lists all requirements by status; approved ones form the baseline. Narrative documents are generated on request.",
    `<a class="btn primary" href="/api/projects/${pid}/export">${I("download", 15)}Download all (.zip)</a>`);
  if (!d.requirements.length) return head + `<div class="card">${empty("download", "Nothing to export yet", "Run an analysis first.")}</div>`;
  const by = (s) => d.requirements.filter((r) => r.approval_status === s);
  return head + `
  <div class="callout ${art ? "ok" : "info"}" style="margin-bottom:14px">${I(art ? "check" : "chat", 16)}<div>${art ? `<b>Stories and use cases generated</b> (${plural(art.stories.length, "story", "stories")}, ${plural(art.use_cases.length, "use case")}).` : "<b>User stories and use cases are not generated yet.</b> They take one model call."} <button class="linkbtn" data-act="gen-docs">${art ? "Regenerate" : "Generate stories and use cases"}</button></div></div>
  <div class="card" style="margin-bottom:16px"><div class="list">${FILES.map(([name, desc, icon, binary]) => `<div class="fileitem">${I(icon, 20)}<div class="meta"><b>${esc(name)}</b><div class="sm muted">${esc(desc)}</div></div>
    ${binary ? "" : `<button class="btn sm" data-act="preview-file" data-f="${esc(name)}">${I("eye", 14)}Preview</button>`}<a class="btn sm" href="/api/projects/${pid}/export/${esc(name)}" download="${esc(name)}">${I("download", 14)}Download</a></div>`).join("")}</div></div>
  <div class="card"><div class="card-h"><div><h2>Requirements by status</h2><p>The same lists the requirements report contains</p></div></div>
    <div class="grid g2" style="gap:0"><div style="padding:14px 18px;border-right:1px solid var(--border)"><div class="row" style="margin-bottom:8px">${pill(`Approved ${by("approved").length}`, "ok")}</div>${by("approved").map((r) => `<div class="sm" style="padding:5px 0"><span class="mono xs muted">${esc(r.ref)}</span> ${esc(r.statement)}</div>`).join("") || '<span class="muted sm">None yet.</span>'}</div>
    <div style="padding:14px 18px"><div class="row" style="margin-bottom:8px">${pill(`Needs revision ${by("needs_revision").length}`, "warn")}${pill(`Pending ${by("pending").length}`)}</div>${[...by("needs_revision"), ...by("pending")].map((r) => { const q = openQs().filter((x) => x.requirement_id === r.id); return `<div class="sm" style="padding:5px 0"><span class="mono xs muted">${esc(r.ref)}</span> ${esc(r.statement)}${q.map((x) => `<div class="xs muted" style="padding-left:12px">Open question: ${esc(x.question)}</div>`).join("")}</div>`; }).join("") || '<span class="muted sm">Everything decided.</span>'}</div></div></div>`;
};

/* =================================================== side panels built on demand */
function textDrawer(title, subtitle, body) {
  return `<div class="scrim" data-act="close-drawer"></div><aside class="drawer"><div class="drawer-h"><div><h2>${esc(title)}</h2><div class="sm muted" style="margin-top:3px">${esc(subtitle || "")}</div></div><button class="btn sm icon-only ghost" data-act="close-drawer" aria-label="Close">${I("x", 18)}</button></div><div class="drawer-b">${body}</div></aside>`;
}
function kbDrawer(kb) {
  const q = (K.S.drafts["kb-search"] || "").toLowerCase();
  const items = kb.clauses.filter((c) => !q || `${c.id} ${c.source} ${c.title} ${c.text}`.toLowerCase().includes(q));
  return textDrawer("Knowledge base", `${kb.version} · ${kb.clauses.length} clauses · ${kb.controls} controls`,
    `<div class="callout warn">${I("alert", 15)}<div>Paraphrased summaries for prototyping, not legal text. Verify against the official source.</div></div>
    <input class="input" data-draft="kb-search" id="kb-search" placeholder="Search clauses" value="${esc(K.S.drafts["kb-search"] || "")}">
    ${items.map((c) => `<div class="card" style="padding:12px 14px"><div class="row between"><b class="sm">${esc(c.title)}</b><span class="row" style="gap:5px">${pill(c.jurisdiction)}${c.high_impact ? pill("high impact", "warn") : ""}</span></div><div class="xs muted" style="margin:3px 0">${esc(c.source)} · ${esc(c.id)} · effective ${esc(c.effective)}</div><div class="sm">${esc(c.text)}</div></div>`).join("")}`);
}
