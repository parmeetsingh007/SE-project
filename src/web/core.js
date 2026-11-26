/* KYCompass web app: shared state, API client, helpers. Plain JS, no build step. */
"use strict";

const K = {
  S: {
    page: "Overview", pid: null, d: null, projects: [], health: null, samples: [], demos: [], kb: null,
    drafts: {}, files: [], startMode: "paste", inputMode: "paste", jurisdictions: ["IN"],
    f: { rqStatus: "all", rqCat: "", rqSearch: "", rqWeak: false, rqOrigin: "all", qStatus: "open", riskCell: "", auditLlm: false, legalOnly: false },
    drawer: null, editing: false, busy: false, panelOpen: true, panelMin: false,
    identity: { user: "Guest", role: "business_analyst" },
    lastJobSig: "", dismissedJob: "", seenJobs: new Set(),
  },
  ACTIONS: {},
  PAGES: {},
};

/* ---------------------------------------------------------------------- helpers */
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const cap = (s) => (s ? String(s).replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase()) : "");
const plural = (n, w, pl) => `${n} ${n === 1 ? w : pl || w + "s"}`;
const pct = (n) => `${Math.round((n || 0) * 100)}%`;
const fmtDur = (s) => (s < 90 ? `${Math.round(s)}s` : `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`);
const fmtTime = (iso) => { try { return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }); } catch { return iso || ""; } };
const initials = (n) => (n || "?").split(/\s+/).map((p) => p[0]).slice(0, 2).join("").toUpperCase();

const ICONS = {
  spark: '<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"/><path d="M19 15l.9 2.1L22 18l-2.1.9L19 21l-.9-2.1L16 18l2.1-.9z"/>',
  file: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><path d="M9 13h6M9 17h6"/>',
  upload: '<path d="M12 16V4"/><path d="m7 9 5-5 5 5"/><path d="M5 20h14"/>',
  list: '<path d="M8 6h13M8 12h13M8 18h13"/><path d="M3 6h.01M3 12h.01M3 18h.01"/>',
  help: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.7.4-1 1-1 1.7"/><path d="M12 17h.01"/>',
  alert: '<path d="M12 3 2 20h20z"/><path d="M12 10v4M12 17h.01"/>',
  shield: '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="m9 12 2 2 4-4"/>',
  flow: '<rect x="3" y="3" width="6" height="6" rx="1"/><rect x="15" y="15" width="6" height="6" rx="1"/><path d="M9 6h4a2 2 0 0 1 2 2v7"/>',
  check: '<path d="m5 12 5 5 9-10"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  edit: '<path d="M4 20h4L19 9l-4-4L4 16z"/>',
  send: '<path d="M22 2 11 13"/><path d="M22 2l-7 20-4-9-9-4z"/>',
  refresh: '<path d="M20 11a8 8 0 0 0-14.5-3.5L4 9"/><path d="M4 4v5h5"/><path d="M4 13a8 8 0 0 0 14.5 3.5L20 15"/><path d="M20 20v-5h-5"/>',
  download: '<path d="M12 4v12"/><path d="m7 11 5 5 5-5"/><path d="M5 20h14"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5 19 19M5 19l1.5-1.5M17.5 6.5 19 5"/>',
  moon: '<path d="M21 13A9 9 0 1 1 11 3a7 7 0 0 0 10 10z"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  trash: '<path d="M4 7h16M10 11v6M14 11v6"/><path d="M6 7l1 13h10l1-13M9 7V4h6v3"/>',
  chev: '<path d="m6 9 6 6 6-6"/>',
  arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  lock: '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
  search: '<circle cx="11" cy="11" r="6"/><path d="m20 20-4-4"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  book: '<path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z"/><path d="M4 19V5"/>',
  grid: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  stamp: '<path d="M5 21h14M7 17h10v-3a3 3 0 0 0-2-2.8V8a3 3 0 1 0-6 0v3.2A3 3 0 0 0 7 14z"/>',
  scale: '<path d="M12 3v18M5 21h14M5 7h14"/><path d="m5 7-3 7a3 3 0 0 0 6 0zM19 7l-3 7a3 3 0 0 0 6 0z"/>',
  pulse: '<path d="M3 12h4l3-8 4 16 3-8h4"/>',
  home: '<path d="M3 11 12 3l9 8"/><path d="M5 10v10h14V10"/>',
  menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
  compass: '<circle cx="12" cy="12" r="9"/><path d="m15.5 8.5-2 5-5 2 2-5z"/>',
  eye: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  chat: '<path d="M21 12a8 8 0 0 1-11.6 7.1L3 21l1.9-5.4A8 8 0 1 1 21 12z"/>',
};
const I = (name, size = 16) => `<svg class="icon" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ""}</svg>`;

const pill = (text, kind = "") => `<span class="pill ${kind}">${esc(text)}</span>`;
const STATUS_KIND = { approved: "ok", pending: "", needs_revision: "warn", rejected: "bad" };
const statusPill = (s) => pill(cap(s), STATUS_KIND[s] || "");
const riskPill = (l) => (l ? pill(`${cap(l)} risk`, { high: "bad", medium: "warn", low: "ok" }[l]) : "");
const tags = (list, cls = "") => `<div class="tags">${(list || []).map((t) => `<span class="tag ${cls}">${esc(cap(t))}</span>`).join("")}</div>`;
const empty = (icon, title, text, action = "") => `<div class="empty">${I(icon, 30)}<h3>${esc(title)}</h3><p>${esc(text)}</p>${action}</div>`;
const pageHead = (title, sub = "", actions = "") => `<div class="page-head"><div><h1>${esc(title)}</h1>${sub ? `<p>${sub}</p>` : ""}</div>${actions ? `<div class="actions">${actions}</div>` : ""}</div>`;
const confBar = (c) => `<span class="conf"><span class="bar ${c >= 0.75 ? "ok" : c >= 0.5 ? "warn" : "bad"}"><span style="width:${Math.round(c * 100)}%"></span></span>${pct(c)}</span>`;
const reqTag = (ref) => `<button class="tag mono" data-act="open-req-ref" data-ref="${esc(ref)}">${esc(ref)}</button>`;

/* ----------------------------------------------------------------------- API */
async function api(method, path, body, opts = {}) {
  const headers = { "X-User": K.S.identity.user, "X-Role": K.S.identity.role };
  let payload;
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }
  const res = await fetch(path, { method, headers, body: payload });
  if (!res.ok) {
    let detail = res.statusText;
    try { const j = await res.json(); detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch { /* keep statusText */ }
    const err = new Error(detail);
    err.status = res.status;
    throw err;
  }
  const type = res.headers.get("content-type") || "";
  if (opts.text || !type.includes("json")) return res.text();
  return res.json();
}
const GET = (p) => api("GET", p);
const POST = (p, b = {}) => api("POST", p, b);

function toast(message, bad = false) {
  const el = document.createElement("div");
  el.className = "toast" + (bad ? " bad" : "");
  el.textContent = message;
  $("#toasts").appendChild(el);
  setTimeout(() => el.remove(), bad ? 6500 : 3200);
}

async function guard(fn, fallback = "Something went wrong") {
  try { return await fn(); } catch (e) { toast(e.message || fallback, true); return undefined; }
}

/* identity + theme persist in localStorage (best effort) */
function loadPrefs() {
  try {
    const id = JSON.parse(localStorage.getItem("kycompass.identity") || "null");
    if (id && id.user && id.role) K.S.identity = id;
  } catch { /* ignore */ }
}
function savePrefs() { try { localStorage.setItem("kycompass.identity", JSON.stringify(K.S.identity)); } catch { /* ignore */ } }
function toggleTheme() {
  const cur = document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  const next = cur === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem("kycompass.theme", next); } catch { /* ignore */ }
}
