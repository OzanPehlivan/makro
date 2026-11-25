"use strict";

// --- Kimlik doğrulama ve API ---
const TOKEN = (() => {
  const m = location.hash.match(/t=([\w-]+)/);
  if (m) {
    try { sessionStorage.setItem("mt", m[1]); } catch (e) { /* yoksay */ }
    history.replaceState(null, "", "/");
    return m[1];
  }
  try { return sessionStorage.getItem("mt") || ""; } catch (e) { return ""; }
})();

async function api(path, body) {
  const opts = { headers: { "X-Token": TOKEN } };
  if (body !== undefined) {
    opts.method = "POST";
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Hata ${res.status}`);
  return data;
}
const cmd = (name, extra = {}) => api("/api/cmd", { cmd: name, ...extra });

// --- Sabitler ---
const ACTIONS = {
  click: { label: "Tıklama", icon: "i-click", desc: "Fare tıklamasını istediğin hızda tekrarlar." },
  spam: { label: "Tuş tekrarı", icon: "i-repeat", desc: "Seçtiğin tuşa saniyede istediğin kadar basar." },
  text: { label: "Metin yaz", icon: "i-text", desc: "Kelime, cümle veya paragraf yazar. Türkçe karakter ve emoji olur." },
  seq: { label: "Makro dizisi", icon: "i-seq", desc: "Tuş, tıklama, metin ve beklemelerden oluşan sıra. Kaydedebilirsin." },
  remap: { label: "Tuş ata", icon: "i-remap", desc: "Bu tuş başka bir tuş, kısayol veya fare tuşu gibi davranır." },
  launch: { label: "Program aç", icon: "i-launch", desc: "Program, dosya, klasör veya web sitesi açar." },
  disable: { label: "Devre dışı", icon: "i-disable", desc: "Tuş hiçbir şey yapmaz (ör. oyunda Windows tuşu)." },
};
const MODES = {
  click: ["hold", "toggle"], spam: ["hold", "toggle"], text: ["press"], seq: ["press", "hold", "toggle"],
  remap: ["hold"], launch: ["press"], disable: ["hold"],
};
const MODE_INFO = {
  hold: ["Basılı tut", "Tuş basılıyken çalışır, bırakınca durur."],
  toggle: ["Aç / kapat", "Bir basışta başlar, tekrar basınca durur."],
  press: ["Bir kez", "Her basışta bir kez çalışır."],
};
const BUTTONS = { left: "Sol tık", right: "Sağ tık", middle: "Orta tık", x1: "Fare 4", x2: "Fare 5" };
const BUTTON_VK = { left: 1, right: 2, middle: 4, x1: 5, x2: 6 };
const VK_BUTTON = { 1: "left", 2: "right", 4: "middle", 5: "x1", 6: "x2" };
const MOD_LABEL = { ctrl: "Ctrl", shift: "Shift", alt: "Alt", win: "Win" };
const MOD_ORDER = ["ctrl", "shift", "alt", "win"];
const IGNORED_EXES = new Set(["msedge.exe", "chrome.exe", "explorer.exe", "pythonw.exe", "python.exe", "searchhost.exe", "shellexperiencehost.exe", "startmenuexperiencehost.exe", ""]);

// Klavye çizimi: x, y, genişlik, yükseklik (tuş birimi). sc: düzene göre değişen tuş, vk: sabit tuş
const KB = (() => {
  const k = [];
  const add = (o) => k.push({ w: 1, h: 1, ...o });
  add({ vk: 0x1b, x: 0, y: 0, l: "Esc" });
  [[2, 0x70], [3, 0x71], [4, 0x72], [5, 0x73], [6.5, 0x74], [7.5, 0x75], [8.5, 0x76], [9.5, 0x77], [11, 0x78], [12, 0x79], [13, 0x7a], [14, 0x7b]]
    .forEach(([x, vk]) => add({ vk, x, y: 0 }));
  add({ vk: 0x2c, x: 15.25, y: 0, l: "PrtSc" }); add({ vk: 0x91, x: 16.25, y: 0, l: "ScrLk" }); add({ vk: 0x13, x: 17.25, y: 0, l: "Pause" });
  const r1 = 1.25, r2 = 2.25, r3 = 3.25, r4 = 4.25, r5 = 5.25;
  add({ sc: 0x29, x: 0, y: r1 });
  for (let i = 0; i < 12; i++) add({ sc: 0x02 + i, x: 1 + i, y: r1 });
  add({ vk: 0x08, x: 13, y: r1, w: 2, l: "⌫" });
  add({ vk: 0x09, x: 0, y: r2, w: 1.5, l: "Tab" });
  for (let i = 0; i < 12; i++) add({ sc: 0x10 + i, x: 1.5 + i, y: r2 });
  add({ vk: 0x0d, x: 13.75, y: r2, w: 1.25, h: 2, l: "Enter" });
  add({ vk: 0x14, x: 0, y: r3, w: 1.75, l: "Caps" });
  for (let i = 0; i < 11; i++) add({ sc: 0x1e + i, x: 1.75 + i, y: r3 });
  add({ sc: 0x2b, x: 12.75, y: r3 });
  add({ vk: 0xa0, x: 0, y: r4, w: 1.25, l: "Shift" });
  add({ sc: 0x56, x: 1.25, y: r4 });
  for (let i = 0; i < 10; i++) add({ sc: 0x2c + i, x: 2.25 + i, y: r4 });
  add({ vk: 0xa1, x: 12.25, y: r4, w: 2.75, l: "Shift" });
  [[0xa2, 0, "Ctrl"], [0x5b, 1.25, "Win"], [0xa4, 2.5, "Alt"]].forEach(([vk, x, l]) => add({ vk, x, y: r5, w: 1.25, l }));
  add({ vk: 0x20, x: 3.75, y: r5, w: 6.25, l: "" });
  [[0xa5, 10, "AltGr"], [0x5c, 11.25, "Win"], [0x5d, 12.5, "Menü"], [0xa3, 13.75, "Ctrl"]].forEach(([vk, x, l]) => add({ vk, x, y: r5, w: 1.25, l }));
  [[0x2d, 15.25, r1, "Ins"], [0x24, 16.25, r1, "Home"], [0x21, 17.25, r1, "PgUp"], [0x2e, 15.25, r2, "Del"], [0x23, 16.25, r2, "End"], [0x22, 17.25, r2, "PgDn"],
    [0x26, 16.25, r4, "↑"], [0x25, 15.25, r5, "←"], [0x28, 16.25, r5, "↓"], [0x27, 17.25, r5, "→"]].forEach(([vk, x, y, l]) => add({ vk, x, y, l }));
  [[0x90, 18.5, r1, "Num"], [0x6f, 19.5, r1, "/"], [0x6a, 20.5, r1, "*"], [0x6d, 21.5, r1, "−"],
    [0x67, 18.5, r2, "7"], [0x68, 19.5, r2, "8"], [0x69, 20.5, r2, "9"], [0x64, 18.5, r3, "4"], [0x65, 19.5, r3, "5"], [0x66, 20.5, r3, "6"],
    [0x61, 18.5, r4, "1"], [0x62, 19.5, r4, "2"], [0x63, 20.5, r4, "3"], [0x6e, 20.5, r5, ","]].forEach(([vk, x, y, l]) => add({ vk, x, y, l }));
  add({ vk: 0x6b, x: 21.5, y: r2, h: 2, l: "+" });
  add({ vk: 0x0d, x: 21.5, y: r4, h: 2, l: "↵", dup: true });
  add({ vk: 0x60, x: 18.5, y: r5, w: 2, l: "0" });
  return k;
})();

// --- Durum ---
const S = {
  config: null, status: {}, keys: {}, scanMap: {}, autostart: false, version: "",
  view: null, // görüntülenen profil id
  sel: null, // { vk, bid }
  draft: null, // { b: binding, isNew }
  dirty: false,
  recentExes: [],
  captureResolve: null,
  recordStart: 0,
  recordMouse: false,
  online: true,
};

// --- Yardımcılar ---
const $ = (id) => document.getElementById(id);
const clone = (o) => JSON.parse(JSON.stringify(o));
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const icon = (id) => `<svg><use href="#${id}"/></svg>`;
const newId = () => Array.from(crypto.getRandomValues(new Uint8Array(6)), (b) => b.toString(16).padStart(2, "0")).join("");
const keyName = (vk) => S.keys[vk] || `VK ${vk}`;
const profile = () => S.config.profiles.find((p) => p.id === S.view) || S.config.profiles[0];
const sameTrig = (a, b) => a.vk === b.vk && a.mods.join() === b.mods.join();
const trigText = (t) => [...t.mods.map((m) => MOD_LABEL[m]), keyName(t.vk)].join(" + ");
const trigHTML = (t) => `<span class="trig">${[...t.mods.map((m) => MOD_LABEL[m]), keyName(t.vk)].map((x) => `<kbd>${esc(x)}</kbd>`).join("")}</span>`;
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

function toast(msg, kind = "") {
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = msg;
  $("toasts").appendChild(el);
  setTimeout(() => el.remove(), kind === "err" ? 6000 : 2600);
}

function summary(b) {
  const a = b.action;
  switch (a.type) {
    case "click": return `${BUTTONS[a.button]} · ${a.cps} CPS`;
    case "spam": return `${a.key ? trigText(a.key) : "?"} · saniyede ${a.rate}`;
    case "text": return a.text ? `“${a.text.replace(/\s+/g, " ").slice(0, 40)}${a.text.length > 40 ? "…" : ""}”` : "Boş metin";
    case "seq": return `${a.steps.length} adım${b.mode === "press" && a.repeat > 1 ? ` · ${a.repeat} kez` : ""}`;
    case "remap": return a.target ? `→ ${trigText(a.target)}` : "Hedef seçilmedi";
    case "launch": return a.target.split(/[\\/]/).filter(Boolean).pop() || a.target;
    default: return "Tuş kapalı";
  }
}
const shortSub = (b) => {
  const a = b.action;
  if (a.type === "click") return `${a.cps}`;
  if (a.type === "spam") return `${a.rate}/s`;
  if (a.type === "remap" && a.target) return keyName(a.target.vk);
  return ACTIONS[a.type].label;
};

function defaultAction(type) {
  return {
    click: { type, button: "left", cps: 20 },
    spam: { type, key: null, rate: 20 },
    text: { type, text: "", method: "unicode", delay: 0, enter: false },
    seq: { type, steps: [], repeat: 1 },
    remap: { type, target: null },
    launch: { type, target: "", args: "" },
    disable: { type },
  }[type];
}

function bindingsFor(vk, p = profile()) {
  return p.bindings.filter((b) => b.trigger.vk === vk)
    .sort((a, b) => a.trigger.mods.length - b.trigger.mods.length);
}

function isLive(p) {
  return S.status.profile === p.id;
}

function confirmDiscard() {
  if (!S.dirty) return true;
  if (!confirm("Kaydedilmemiş değişiklikler silinsin mi?")) return false;
  S.dirty = false;
  return true;
}

// --- Kaydetme ---
async function saveConfig(cfg, okMsg) {
  try {
    const res = await api("/api/config", cfg);
    S.config = res.config;
    if (okMsg) toast(okMsg, "ok");
    return true;
  } catch (e) {
    toast(e.message, "err");
    return false;
  }
}

// --- Çizim: üst çubuk ---
function renderTop() {
  const tabs = S.config.profiles.map((p) => `
    <button class="ptab ${p.id === S.view ? "sel" : ""}" data-act="view-profile" data-id="${p.id}" title="${isLive(p) ? "Şu an aktif" : ""}">
      <span class="pdot ${isLive(p) ? "on" : ""}"></span>${esc(p.name)}
      ${p.apps.length ? `<span class="papps">${p.apps.length} uyg.</span>` : ""}
    </button>`).join("");
  $("profiles").innerHTML = tabs;

  const live = S.config.profiles.find((p) => p.id === S.status.profile);
  $("live").innerHTML = live
    ? `Aktif: <b>${esc(live.name)}</b>${S.status.exe ? ` · ${esc(S.status.exe)}` : ""}`
    : "Motor bekleniyor…";

  const on = S.status.enabled !== false;
  const m = $("master");
  m.classList.toggle("off", !on);
  m.setAttribute("aria-checked", on);
  m.querySelector(".master-label").textContent = on ? "Makrolar açık" : "Makrolar kapalı";
  m.title = `Kısayol: ${trigText(S.config.toggle_hotkey)}`;
}

function renderProfileHead() {
  const p = profile();
  const isDefault = S.config.active_profile === p.id;
  $("profile-head").innerHTML = `
    <h1>${esc(p.name)}</h1>
    <div class="apps">
      ${isLive(p) ? `<span class="chip ok">● Şu an aktif</span>` : ""}
      ${isDefault ? `<span class="chip accent">Varsayılan profil</span>` : `<button class="btn sm ghost" data-act="make-default">Varsayılan yap</button>`}
      ${p.apps.map((a) => `<span class="chip">${icon("i-app")}${esc(a)}</span>`).join("")}
    </div>
    <div class="spacer"></div>
    <button class="btn sm" data-act="profile-settings">${icon("i-gear")}Profil ayarları</button>`;
}

// --- Çizim: klavye ---
function renderKeyboard() {
  const p = profile();
  const active = new Set(isLive(p) ? S.status.active || [] : []);
  const hk = S.config.toggle_hotkey;
  $("kb").innerHTML = KB.map((k) => {
    const vk = k.vk ?? S.scanMap[k.sc];
    if (!vk) return "";
    const list = bindingsFor(vk, p);
    const enabled = list.filter((b) => b.enabled);
    const main = enabled.find((b) => !b.trigger.mods.length) || enabled[0];
    const combos = enabled.filter((b) => b.trigger.mods.length).length;
    const cls = ["key"];
    if (list.length) cls.push("bound");
    if (list.length && !enabled.length) cls.push("off");
    if (enabled.some((b) => active.has(b.id))) cls.push("active");
    if (S.sel && S.sel.vk === vk) cls.push("sel");
    const isHk = hk.vk === vk && !hk.mods.length;
    if (isHk && !list.length) cls.push("hotkey");
    // Dar tuşlarda sadece simge, geniş tuşlarda simge + kısa açıklama
    const wide = k.w >= 1.5;
    let sub = "";
    if (main) sub = icon(ACTIONS[main.action.type].icon) + (wide ? `<span>${esc(shortSub(main))}</span>` : "");
    else if (isHk) sub = wide ? "<span>Aç/Kapat</span>" : icon("i-power");
    const label = k.l !== undefined ? k.l : keyName(vk);
    if (label.length > 3 && !wide) cls.push("small");
    const style = `left:calc(var(--u)*${k.x});top:calc(var(--u)*${k.y});width:calc(var(--u)*${k.w} - 4px);height:calc(var(--u)*${k.h} - 4px)`;
    const title = list.length ? list.map((b) => `${trigText(b.trigger)}: ${b.name || ACTIONS[b.action.type].label}`).join("\n") : keyName(vk);
    return `<div class="${cls.join(" ")}" style="${style}" data-act="select-key" data-vk="${vk}" title="${esc(title)}">
      <span class="lbl">${esc(label)}</span><span class="sub">${sub}</span>
      ${combos ? `<span class="dots">${"<i></i>".repeat(Math.min(combos, 3))}</span>` : ""}
    </div>`;
  }).join("");
}

function fitKeyboard() {
  const w = $("kb-wrap").clientWidth;
  const u = clamp(Math.floor(w / 22.5), 24, 50);
  const kb = $("kb");
  kb.style.setProperty("--u", `${u}px`);
  kb.style.width = `${u * 22.5}px`;
  kb.style.height = `${u * 6.25}px`;
}

function renderMouse() {
  const p = profile();
  const active = new Set(isLive(p) ? S.status.active || [] : []);
  const btn = (cls, vk, label, locked) => {
    const list = bindingsFor(vk, p).filter((b) => b.enabled);
    const c = ["mbtn", cls];
    if (locked) c.push("locked");
    if (list.length) c.push("bound");
    if (list.some((b) => active.has(b.id))) c.push("active");
    if (S.sel && S.sel.vk === vk) c.push("sel");
    const title = locked ? "Sol ve sağ tık tetik olamaz" : list.length ? list.map((b) => `${trigText(b.trigger)}: ${summary(b)}`).join("\n") : keyName(vk);
    return `<div class="${c.join(" ")}" ${locked ? "" : `data-act="select-key" data-vk="${vk}"`} title="${esc(title)}">${label}</div>`;
  };
  $("mouse").innerHTML = `<div class="body"></div>
    ${btn("l", 1, "Sol", true)}${btn("r", 2, "Sağ", true)}${btn("m", 4, "M3")}${btn("x2", 6, "5")}${btn("x1", 5, "4")}`;
}

function renderList() {
  const p = profile();
  const active = new Set(isLive(p) ? S.status.active || [] : []);
  $("bind-count").textContent = `${p.bindings.length} atama`;
  if (!p.bindings.length) {
    $("bind-list").innerHTML = `<div class="empty">Henüz atama yok. Klavyede bir tuşa tıklayarak başla.</div>`;
    return;
  }
  const sorted = [...p.bindings].sort((a, b) => trigText(a.trigger).localeCompare(trigText(b.trigger), "tr"));
  $("bind-list").innerHTML = sorted.map((b) => `
    <div class="bind-row ${b.enabled ? "" : "off"} ${active.has(b.id) ? "active" : ""} ${S.sel && S.sel.bid === b.id ? "sel" : ""}" data-act="select-binding" data-id="${b.id}">
      <div class="bicon">${icon(ACTIONS[b.action.type].icon)}</div>
      <div class="bmain">
        <div class="bname">${esc(b.name || ACTIONS[b.action.type].label)}</div>
        <div class="bdesc">${esc(summary(b))} · ${MODE_INFO[b.mode][0]}</div>
      </div>
      ${trigHTML(b.trigger)}
      <label class="switch" title="Etkin" data-stop><input type="checkbox" data-act="toggle-binding" data-id="${b.id}" ${b.enabled ? "checked" : ""}><i></i></label>
    </div>`).join("");
}

// --- Çizim: sağ panel ---
function renderPanel() {
  const panel = $("panel");
  if (!S.sel) {
    const hk = S.config.toggle_hotkey;
    panel.innerHTML = `
      <div class="panel-empty">
        <h3>Bir tuş seç</h3>
        <p>Klavyede ya da faredeki bir tuşa tıkla, ona istediğin işi ata. Her tuş farklı bir iş yapabilir; Ctrl/Shift/Alt kombinasyonlarıyla aynı tuşa birden fazla iş verebilirsin.</p>
        <div class="tips">
          <div class="tip"><div class="ticon">${icon("i-click")}</div><div><b>Tıklama ve tuş tekrarı</b><span>Saniyede 1000'e kadar, kaymayan hassas zamanlama.</span></div></div>
          <div class="tip"><div class="ticon">${icon("i-text")}</div><div><b>Metin yaz</b><span>Tek tuşla kelime, cümle, şablon mesaj. Türkçe karakter sorunsuz.</span></div></div>
          <div class="tip"><div class="ticon">${icon("i-seq")}</div><div><b>Makro dizisi</b><span>Kayıt düğmesine bas, yaptıklarını beklemeleriyle birlikte kaydet.</span></div></div>
          <div class="tip"><div class="ticon">${icon("i-power")}</div><div><b>Hızlı aç/kapat</b><span><kbd>${esc(trigText(hk))}</kbd> tüm makroları anında açıp kapatır.</span></div></div>
        </div>
      </div>`;
    return;
  }
  const { vk } = S.sel;
  const list = bindingsFor(vk);
  const d = S.draft;
  const tabs = list.map((b) => `<button class="ctab ${d && !d.isNew && d.b.id === b.id ? "sel" : ""}" data-act="select-binding" data-id="${b.id}">${icon(ACTIONS[b.action.type].icon)}${esc(trigText(b.trigger))}</button>`).join("");
  panel.innerHTML = `
    <div class="panel-head">
      <div class="bigkey">${esc(keyName(vk))}</div>
      <div>
        <h3>${VK_BUTTON[vk] ? esc(keyName(vk)) : `${esc(keyName(vk))} tuşu`}</h3>
        <p>${list.length ? `${list.length} atama` : "Henüz atama yok"}</p>
      </div>
      <div class="spacer"></div>
      <button class="icon-btn" data-act="close-panel" title="Kapat">${icon("i-x")}</button>
    </div>
    <div class="combo-tabs">${tabs}<button class="ctab ${d && d.isNew ? "sel" : ""}" data-act="new-binding">${icon("i-plus")}Yeni atama</button></div>
    ${d ? editorHTML(d) : ""}`;
}

function editorHTML(d) {
  const b = d.b;
  const a = b.action;
  const t = a.type;
  const types = Object.entries(ACTIONS).map(([k, v]) => `
    <button class="type ${t === k ? "sel" : ""}" data-act="set-type" data-type="${k}" title="${esc(v.desc)}">${icon(v.icon)}${v.label}</button>`).join("");
  const modes = MODES[t];
  const modeSeg = modes.length > 1 ? `
    <div class="field">
      <div class="field-title">Çalışma şekli</div>
      <div class="seg">${modes.map((m) => `<button class="${b.mode === m ? "on" : ""}" data-act="set-mode" data-mode="${m}">${MODE_INFO[m][0]}</button>`).join("")}</div>
      <p class="desc">${MODE_INFO[b.mode][1]}</p>
    </div>` : "";
  const canBlock = !["remap", "disable"].includes(t);
  return `
    <div class="editor">
      <div class="field">
        <div class="field-title">Tetik <small>Kombinasyon için değiştiricileri seç</small></div>
        <div class="trigger-box">
          ${MOD_ORDER.map((m) => `<button class="modtog ${b.trigger.mods.includes(m) ? "on" : ""}" data-act="toggle-mod" data-mod="${m}">${MOD_LABEL[m]}</button>`).join("")}
          <span style="color:var(--faint)">+</span>
          <button class="keybtn" data-act="capture-trigger" title="Değiştirmek için tıkla, sonra tuşa bas">${icon("i-key")}${esc(keyName(b.trigger.vk))}</button>
        </div>
      </div>
      <div class="field">
        <div class="field-title">Ne yapsın?</div>
        <div class="types">${types}</div>
        <p class="desc">${ACTIONS[t].desc}</p>
      </div>
      ${actionFields(b)}
      ${modeSeg}
      <div class="field">
        <label for="f-name">Ad <small style="font-weight:400;color:var(--faint)">isteğe bağlı</small></label>
        <input class="input" id="f-name" data-bind="name" maxlength="80" placeholder="${esc(ACTIONS[t].label)}" value="${esc(b.name)}">
      </div>
      ${canBlock ? toggleRow("block", "Orijinal tuşu engelle", "Açıkken tuşun kendi işlevi (ör. harf yazması) çalışmaz.", b.block) : ""}
      ${toggleRow("enabled", "Etkin", "Kapatırsan ayarlar kalır ama tuş çalışmaz.", b.enabled)}
    </div>
    <div class="editor-foot">
      ${!d.isNew ? `<button class="btn danger" data-act="delete-binding" title="Atamayı sil">${icon("i-trash")}</button>` : ""}
      <button class="btn ghost" data-act="revert">Vazgeç</button>
      <button class="btn primary" data-act="save-binding">${S.dirty ? `<span class="dirty-dot"></span>` : ""}${d.isNew ? "Atamayı ekle" : "Kaydet"}</button>
    </div>`;
}

function toggleRow(key, title, desc, on) {
  return `<div class="toggle-row"><div><b>${title}</b><span>${desc}</span></div>
    <label class="switch"><input type="checkbox" data-bind="${key}" ${on ? "checked" : ""}><i></i></label></div>`;
}

function rateField(label, key, value, unit) {
  return `<div class="field">
    <div class="field-title">${label} <small>1 – 1000 ${unit}</small></div>
    <div class="rate">
      <input type="range" min="1" max="1000" value="${value}" data-rate="${key}">
      <input class="input" type="number" min="1" max="1000" value="${value}" data-rate="${key}">
    </div>
    <div class="presets">${[5, 10, 20, 50, 100, 200, 500, 1000].map((v) => `<button data-act="preset" data-key="${key}" data-v="${v}">${v}</button>`).join("")}</div>
  </div>`;
}

function actionFields(b) {
  const a = b.action;
  switch (a.type) {
    case "click":
      return `<div class="field"><div class="field-title">Düğme</div>
        <div class="seg">${Object.entries(BUTTONS).map(([k, v]) => `<button class="${a.button === k ? "on" : ""}" data-act="set-button" data-v="${k}">${v.replace(" tık", "")}</button>`).join("")}</div></div>
        ${rateField("Hız", "cps", a.cps, "CPS")}`;
    case "spam":
      return `<div class="field"><div class="field-title">Basılacak tuş <small>Kısayol da olur (ör. Ctrl + V)</small></div>
        <div class="inline"><button class="keybtn" data-act="capture-target" data-into="key">${icon("i-key")}${a.key ? esc(trigText(a.key)) : "Tuş seç"}</button></div></div>
        ${rateField("Hız", "rate", a.rate, "basış/sn")}`;
    case "text":
      return `<div class="field"><label for="f-text">Yazılacak metin</label>
        <textarea class="input" id="f-text" data-bind="action.text" maxlength="20000" placeholder="Örn: gg wp herkese iyi oyunlar!">${esc(a.text)}</textarea></div>
        <div class="field"><div class="field-title">Yazma yöntemi</div>
          <div class="seg">
            <button class="${a.method === "unicode" ? "on" : ""}" data-act="set-method" data-v="unicode">Her uygulama</button>
            <button class="${a.method === "keys" ? "on" : ""}" data-act="set-method" data-v="keys">Oyun uyumlu</button>
          </div>
          <p class="desc">${a.method === "unicode" ? "Doğrudan karakter gönderir: en hızlısı, emoji ve her dil çalışır." : "Klavye düzenindeki tuşlara basar: yazıyı kabul etmeyen oyunlar için."}</p>
        </div>
        <div class="field"><div class="field-title">Karakter arası gecikme <small>0 = anında</small></div>
          <div class="inline"><input class="input mono" type="number" min="0" max="5000" value="${a.delay}" data-bind="action.delay" data-num="0,5000"><span class="desc">ms</span></div></div>
        ${toggleRow("action.enter", "Sonunda Enter'a bas", "Sohbete yazıp göndermek için.", a.enter)}`;
    case "seq":
      return seqFields(b);
    case "remap": {
      const tg = a.target;
      const isMouse = tg && VK_BUTTON[tg.vk];
      return `<div class="field"><div class="field-title">Hedef</div>
        <div class="seg">
          <button class="${!isMouse ? "on" : ""}" data-act="remap-kind" data-v="key">Klavye tuşu / kısayol</button>
          <button class="${isMouse ? "on" : ""}" data-act="remap-kind" data-v="mouse">Fare tuşu</button>
        </div>
        ${isMouse
          ? `<div class="seg">${Object.entries(BUTTONS).map(([k, v]) => `<button class="${tg.vk === BUTTON_VK[k] ? "on" : ""}" data-act="remap-mouse" data-v="${k}">${v.replace(" tık", "")}</button>`).join("")}</div>`
          : `<div class="inline"><button class="keybtn" data-act="capture-target" data-into="target">${icon("i-key")}${tg ? esc(trigText(tg)) : "Tuş seç"}</button></div>
             <p class="desc">Kısayol atamak için Ctrl/Shift/Alt basılıyken hedef tuşa bas (ör. Ctrl + C).</p>`}
      </div>`;
    }
    case "launch":
      return `<div class="field"><label for="f-target">Program, dosya veya bağlantı</label>
        <div class="inline"><input class="input" id="f-target" data-bind="action.target" placeholder="C:\\Oyunlar\\oyun.exe veya https://..." value="${esc(a.target)}">
        <button class="btn" data-act="browse">Gözat</button></div></div>
        <div class="field"><label for="f-args">Argümanlar <small style="font-weight:400;color:var(--faint)">isteğe bağlı</small></label>
        <input class="input mono" id="f-args" data-bind="action.args" value="${esc(a.args)}"></div>`;
    default:
      return "";
  }
}

const STEP_ICON = { key: "i-key", mouse: "i-mouse", text: "i-text", wait: "i-wait", scroll: "i-scroll" };

function seqFields(b) {
  const a = b.action;
  const steps = a.steps.map((s, i) => {
    let body = "";
    if (s.t === "key") {
      body = `<button class="keybtn" data-act="capture-step" data-i="${i}">${esc(trigText(s))}</button>
        <select class="input" data-step="${i}" data-field="do">
          ${[["tap", "Bas-bırak"], ["down", "Basılı tut"], ["up", "Bırak"]].map(([v, l]) => `<option value="${v}" ${s.do === v ? "selected" : ""}>${l}</option>`).join("")}
        </select>`;
    } else if (s.t === "mouse") {
      body = `<select class="input" data-step="${i}" data-field="btn">${Object.entries(BUTTONS).map(([k, v]) => `<option value="${k}" ${s.btn === k ? "selected" : ""}>${v}</option>`).join("")}</select>
        <select class="input" data-step="${i}" data-field="do">${[["click", "Tıkla"], ["down", "Bas"], ["up", "Bırak"]].map(([v, l]) => `<option value="${v}" ${s.do === v ? "selected" : ""}>${l}</option>`).join("")}</select>`;
    } else if (s.t === "text") {
      body = `<input class="input" style="flex:1;min-width:120px" data-step="${i}" data-field="text" value="${esc(s.text)}" placeholder="Metin">`;
    } else if (s.t === "wait") {
      body = `<span class="desc">Bekle</span><input class="input num" type="number" min="0" max="600000" data-step="${i}" data-field="ms" value="${s.ms}"><span class="desc">ms</span>`;
    } else if (s.t === "scroll") {
      body = `<span class="desc">Kaydır</span><input class="input num" type="number" min="-100" max="100" data-step="${i}" data-field="amount" value="${s.amount}"><span class="desc">+ yukarı / − aşağı</span>`;
    }
    return `<div class="step s-${s.t}">
      <span class="snum">${i + 1}</span><span class="sicon">${icon(STEP_ICON[s.t])}</span>
      <div class="sbody">${body}</div>
      <div class="sacts">
        <button class="icon-btn sm" data-act="step-up" data-i="${i}" title="Yukarı">${icon("i-up")}</button>
        <button class="icon-btn sm" data-act="step-down" data-i="${i}" title="Aşağı">${icon("i-down")}</button>
        <button class="icon-btn sm danger" data-act="step-del" data-i="${i}" title="Sil">${icon("i-x")}</button>
      </div>
    </div>`;
  }).join("");
  const waits = a.steps.filter((s) => s.t === "wait").length;
  return `<div class="field">
      <div class="field-title">Adımlar <small>${a.steps.length} adım</small></div>
      <div class="inline">
        <button class="btn danger" data-act="record">${icon("i-rec")}Kaydet</button>
        <label class="desc" style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="rec-mouse" ${S.recordMouse ? "checked" : ""}> Fare tıklamalarını da kaydet</label>
      </div>
      <div class="steps" id="steps">${steps || `<div class="empty">Adım yok. Aşağıdan ekle ya da kaydet.</div>`}</div>
      <div class="step-add">
        <button class="btn sm" data-act="add-step" data-t="key">${icon("i-key")}Tuş</button>
        <button class="btn sm" data-act="add-step" data-t="mouse">${icon("i-mouse")}Fare</button>
        <button class="btn sm" data-act="add-step" data-t="text">${icon("i-text")}Metin</button>
        <button class="btn sm" data-act="add-step" data-t="wait">${icon("i-wait")}Bekle</button>
        <button class="btn sm" data-act="add-step" data-t="scroll">${icon("i-scroll")}Kaydır</button>
      </div>
      ${a.steps.length ? `<div class="seq-tools">
        ${waits ? `<span class="desc">Tüm beklemeler:</span><input class="input mono" type="number" min="0" max="600000" id="wait-all" value="50">
        <button class="btn sm ghost" data-act="set-waits">Uygula</button><button class="btn sm ghost" data-act="del-waits">Beklemeleri sil</button>` : ""}
        <button class="btn sm ghost" data-act="clear-steps">Temizle</button>
      </div>` : ""}
    </div>
    ${b.mode === "press" ? `<div class="field"><div class="field-title">Tekrar sayısı <small>Her basışta</small></div>
      <div class="inline"><input class="input mono" type="number" min="1" max="100000" value="${a.repeat}" data-bind="action.repeat" data-num="1,100000"><span class="desc">kez</span></div></div>` : ""}`;
}

function renderAll() {
  renderTop();
  renderProfileHead();
  renderKeyboard();
  renderMouse();
  renderList();
  renderPanel();
}

// Durum değişince sadece canlı kısımları yeniden çiz (editördeki odak bozulmasın)
function renderLive() {
  renderTop();
  renderProfileHead();
  renderKeyboard();
  renderMouse();
  renderList();
}

// --- Seçim ve taslak ---
function selectKey(vk) {
  if (!confirmDiscard()) return;
  const list = bindingsFor(vk);
  S.sel = { vk, bid: list[0] ? list[0].id : null };
  S.draft = list[0] ? { b: clone(list[0]), isNew: false } : { b: newBinding(vk), isNew: true };
  S.dirty = false;
  renderAll();
}

function selectBinding(id) {
  if (S.draft && !S.draft.isNew && S.draft.b.id === id) return;
  if (!confirmDiscard()) return;
  const b = profile().bindings.find((x) => x.id === id);
  if (!b) return;
  S.sel = { vk: b.trigger.vk, bid: b.id };
  S.draft = { b: clone(b), isNew: false };
  S.dirty = false;
  renderAll();
}

function newBinding(vk) {
  const used = bindingsFor(vk).map((b) => b.trigger.mods.join());
  const mods = [[], ["ctrl"], ["shift"], ["alt"], ["ctrl", "shift"]].find((m) => !used.includes(m.join())) || [];
  return { id: null, name: "", enabled: true, trigger: { vk, mods }, block: true, mode: "hold", action: defaultAction("click") };
}

function markDirty(rerender = false) {
  S.dirty = true;
  if (rerender) return renderPanel();
  // Yazarken paneli yeniden çizme (odak kaybolur), sadece kaydet düğmesine nokta koy
  const btn = document.querySelector('[data-act="save-binding"]');
  if (btn && !btn.querySelector(".dirty-dot")) btn.insertAdjacentHTML("afterbegin", '<span class="dirty-dot"></span>');
}

function setPath(obj, path, value) {
  const parts = path.split(".");
  const last = parts.pop();
  parts.reduce((o, k) => o[k], obj)[last] = value;
}

function validateDraft(b) {
  const a = b.action;
  if (a.type === "spam" && !a.key) return "Tekrarlanacak tuşu seç.";
  if (a.type === "remap" && !a.target) return "Hedef tuşu seç.";
  if (a.type === "text" && !a.text) return "Yazılacak metni gir.";
  if (a.type === "seq" && !a.steps.length) return "Diziye en az bir adım ekle.";
  if (a.type === "launch" && !a.target.trim()) return "Açılacak programı veya bağlantıyı gir.";
  if (b.enabled) {
    const clash = profile().bindings.find((x) => x.enabled && x.id !== b.id && sameTrig(x.trigger, b.trigger));
    if (clash) return `${trigText(b.trigger)} bu profilde zaten kullanılıyor (${clash.name || ACTIONS[clash.action.type].label}).`;
    if (sameTrig(S.config.toggle_hotkey, b.trigger)) return `${trigText(b.trigger)} makroları aç/kapat kısayolu. Ayarlardan değiştirebilirsin.`;
  }
  return null;
}

async function saveDraft() {
  const d = S.draft;
  const err = validateDraft(d.b);
  if (err) return toast(err, "err");
  const cfg = clone(S.config);
  const p = cfg.profiles.find((x) => x.id === S.view);
  const b = clone(d.b);
  if (d.isNew) {
    b.id = newId();
    p.bindings.push(b);
  } else {
    const i = p.bindings.findIndex((x) => x.id === b.id);
    if (i < 0) p.bindings.push(b); else p.bindings[i] = b;
  }
  if (await saveConfig(cfg, d.isNew ? "Atama eklendi" : "Kaydedildi")) {
    const saved = profile().bindings.find((x) => x.id === b.id);
    S.sel = { vk: saved.trigger.vk, bid: saved.id };
    S.draft = { b: clone(saved), isNew: false };
    S.dirty = false;
    renderAll();
  }
}

async function deleteDraft() {
  const d = S.draft;
  if (!confirm(`"${d.b.name || ACTIONS[d.b.action.type].label}" ataması silinsin mi?`)) return;
  const cfg = clone(S.config);
  const p = cfg.profiles.find((x) => x.id === S.view);
  p.bindings = p.bindings.filter((x) => x.id !== d.b.id);
  if (await saveConfig(cfg, "Atama silindi")) {
    S.dirty = false;
    const vk = S.sel.vk;
    S.sel = null;
    S.draft = null;
    selectKey(vk);
  }
}

// --- Tuş yakalama ve kayıt ---
async function capture() {
  if (S.captureResolve) return null;
  $("capture-overlay").hidden = false;
  const p = new Promise((resolve) => { S.captureResolve = resolve; });
  try {
    await cmd("capture", { value: true });
  } catch (e) {
    toast(e.message, "err");
    finishCapture(null);
  }
  return p;
}

function finishCapture(data) {
  $("capture-overlay").hidden = true;
  const r = S.captureResolve;
  S.captureResolve = null;
  if (r) r(data);
}

let recTimer = null;
async function startRecord() {
  S.recordMouse = $("rec-mouse") ? $("rec-mouse").checked : false;
  try {
    await cmd("record", { value: true, mouse: S.recordMouse });
  } catch (e) {
    return toast(e.message, "err");
  }
  S.recordStart = performance.now();
  $("rec-bar").hidden = false;
  recTimer = setInterval(() => {
    $("rec-time").textContent = `${((performance.now() - S.recordStart) / 1000).toFixed(1)} sn`;
  }, 100);
}

function stopRecord() {
  clearInterval(recTimer);
  $("rec-bar").hidden = true;
  cmd("record", { value: false }).catch((e) => toast(e.message, "err"));
}

function onRecorded(steps) {
  if (!S.draft || S.draft.b.action.type !== "seq") return;
  // Kaydı durdurmak için yapılan son tıklamayı at
  while (steps.length) {
    const s = steps[steps.length - 1];
    if (s.t === "wait" || (s.t === "mouse" && s.btn === "left")) steps.pop(); else break;
  }
  if (!steps.length) return toast("Kayıtta adım yok.");
  S.draft.b.action.steps.push(...steps);
  toast(`${steps.length} adım eklendi`, "ok");
  markDirty(true);
}

// --- Modallar ---
function openModal(html) {
  $("modal-body").innerHTML = html;
  $("modal").hidden = false;
  const first = $("modal-body").querySelector("input, button");
  if (first) first.focus();
}
const closeModal = () => { $("modal").hidden = true; };

let modalState = null;

function profileModal() {
  const p = profile();
  modalState = { name: p.name, apps: [...p.apps] };
  renderProfileModal();
}

function renderProfileModal() {
  const p = profile();
  const m = modalState;
  const recent = S.recentExes.filter((e) => !m.apps.includes(e));
  openModal(`
    <div class="modal-head"><h3>Profil ayarları</h3><button class="icon-btn" data-act="modal-close">${icon("i-x")}</button></div>
    <div class="modal-body">
      <div class="field"><label for="pm-name">Profil adı</label><input class="input" id="pm-name" maxlength="60" value="${esc(m.name)}"></div>
      <div class="field">
        <div class="field-title">Otomatik geçiş uygulamaları <small>Bu uygulama öndeyken profil kendiliğinden açılır</small></div>
        <div class="app-chips">${m.apps.map((a, i) => `<span class="chip accent">${esc(a)}<button data-act="pm-del-app" data-i="${i}" title="Kaldır">${icon("i-x")}</button></span>`).join("") || `<span class="desc">Uygulama yok: bu profil sadece elle seçilince ya da varsayılan olunca çalışır.</span>`}</div>
        <div class="inline"><input class="input mono" id="pm-app" placeholder="ornek.exe"><button class="btn" data-act="pm-add-app">Ekle</button></div>
        ${recent.length ? `<div class="desc">Son kullandıkların:</div><div class="app-chips">${recent.map((e) => `<button class="chip" data-act="pm-add-recent" data-v="${esc(e)}">${icon("i-plus")}${esc(e)}</button>`).join("")}</div>` : `<p class="desc">İpucu: oyunu bir kez öne getirip buraya dönersen adı burada çıkar.</p>`}
      </div>
    </div>
    <div class="modal-foot">
      <div class="left">
        <button class="btn sm ghost" data-act="pm-export" title="Profili dosyaya kaydet">${icon("i-dl")}Dışa aktar</button>
        <button class="btn sm ghost" data-act="pm-duplicate">${icon("i-copy")}Kopyala</button>
        ${S.config.profiles.length > 1 ? `<button class="btn sm danger" data-act="pm-delete">${icon("i-trash")}Sil</button>` : ""}
      </div>
      <button class="btn ghost" data-act="modal-close">Vazgeç</button>
      <button class="btn primary" data-act="pm-save">Kaydet</button>
    </div>`);
  void p;
}

function addProfileModal() {
  openModal(`
    <div class="modal-head"><h3>Yeni profil</h3><button class="icon-btn" data-act="modal-close">${icon("i-x")}</button></div>
    <div class="modal-body">
      <div class="field"><label for="np-name">Profil adı</label><input class="input" id="np-name" maxlength="60" placeholder="Örn: Valorant, Minecraft, İş"></div>
      <div class="field"><div class="field-title">veya dosyadan içe aktar</div>
        <input type="file" id="np-file" accept=".json,application/json" class="desc"></div>
    </div>
    <div class="modal-foot"><button class="btn ghost" data-act="modal-close">Vazgeç</button><button class="btn primary" data-act="np-create">Oluştur</button></div>`);
}

function settingsModal() {
  const c = S.config;
  openModal(`
    <div class="modal-head"><h3>Ayarlar</h3><button class="icon-btn" data-act="modal-close">${icon("i-x")}</button></div>
    <div class="modal-body">
      <div class="field"><div class="field-title">Makroları aç/kapat kısayolu</div>
        <div class="inline"><button class="keybtn" data-act="set-hotkey">${icon("i-key")}${esc(trigText(c.toggle_hotkey))}</button>
        <span class="desc">Her yerde çalışır, oyunun içinde bile.</span></div></div>
      ${toggleRow("auto_switch", "Otomatik profil geçişi", "Profile eklediğin uygulama öne gelince o profile geç.", c.auto_switch).replace('data-bind="auto_switch"', 'data-setting="auto_switch"')}
      ${toggleRow("autostart", "Windows ile başlat", "Bilgisayar açılınca tepside sessizce başlar.", S.autostart).replace('data-bind="autostart"', 'data-setting="autostart"')}
      <p class="about">Pencereyi kapatınca makrolar tepside (saat yanında) çalışmaya devam eder. Tamamen kapatmak için aşağıdaki düğmeyi ya da tepsi menüsünü kullan.<br>Makro Studio ${esc(S.version)}</p>
    </div>
    <div class="modal-foot"><div class="left"><button class="btn danger" data-act="quit">${icon("i-power")}Makro Studio'yu kapat</button></div>
      <button class="btn primary" data-act="modal-close">Tamam</button></div>`);
}

function download(name, data) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

// --- Olaylar ---
const handlers = {
  "view-profile": (el) => {
    if (el.dataset.id === S.view || !confirmDiscard()) return;
    S.view = el.dataset.id;
    S.sel = null;
    S.draft = null;
    renderAll();
  },
  "select-key": (el) => selectKey(+el.dataset.vk),
  "select-binding": (el, ev) => {
    if (ev.target.closest("[data-stop]")) return;
    selectBinding(el.dataset.id);
  },
  "close-panel": () => {
    if (!confirmDiscard()) return;
    S.sel = null;
    S.draft = null;
    renderAll();
  },
  "new-binding": () => {
    if (!confirmDiscard()) return;
    S.draft = { b: newBinding(S.sel.vk), isNew: true };
    S.sel.bid = null;
    S.dirty = false;
    renderAll();
  },
  "set-type": (el) => {
    const b = S.draft.b;
    const t = el.dataset.type;
    if (b.action.type === t) return;
    b.action = defaultAction(t);
    if (!MODES[t].includes(b.mode)) b.mode = MODES[t][0];
    if (t === "remap" || t === "disable") b.block = true;
    markDirty(true);
  },
  "set-mode": (el) => { S.draft.b.mode = el.dataset.mode; markDirty(true); },
  "toggle-mod": (el) => {
    const mods = S.draft.b.trigger.mods;
    const m = el.dataset.mod;
    S.draft.b.trigger.mods = MOD_ORDER.filter((x) => (x === m ? !mods.includes(x) : mods.includes(x)));
    markDirty(true);
  },
  "capture-trigger": async () => {
    const r = await capture();
    if (!r || !S.draft) return;
    if (r.vk === 1 || r.vk === 2) return toast("Sol ve sağ tık tetik olamaz.", "err");
    S.draft.b.trigger = { vk: r.vk, mods: r.mods };
    markDirty(true);
  },
  "capture-target": async (el) => {
    const r = await capture();
    if (!r || !S.draft) return;
    S.draft.b.action[el.dataset.into] = { vk: r.vk, mods: r.mods };
    markDirty(true);
  },
  "set-button": (el) => { S.draft.b.action.button = el.dataset.v; markDirty(true); },
  "set-method": (el) => { S.draft.b.action.method = el.dataset.v; markDirty(true); },
  preset: (el) => { S.draft.b.action[el.dataset.key] = +el.dataset.v; markDirty(true); },
  "remap-kind": (el) => {
    const a = S.draft.b.action;
    const isMouse = a.target && VK_BUTTON[a.target.vk];
    if (el.dataset.v === "mouse" && !isMouse) a.target = { vk: 1, mods: [] };
    if (el.dataset.v === "key" && isMouse) a.target = null;
    markDirty(true);
  },
  "remap-mouse": (el) => { S.draft.b.action.target = { vk: BUTTON_VK[el.dataset.v], mods: [] }; markDirty(true); },
  browse: async () => {
    try {
      const r = await cmd("browse");
      if (r.path) { S.draft.b.action.target = r.path; markDirty(true); }
    } catch (e) { toast(e.message, "err"); }
  },
  "add-step": async (el) => {
    const steps = S.draft.b.action.steps;
    const t = el.dataset.t;
    if (t === "key") {
      const r = await capture();
      if (!r) return;
      steps.push({ t: "key", vk: r.vk, mods: r.mods, do: "tap" });
    } else if (t === "mouse") steps.push({ t: "mouse", btn: "left", do: "click" });
    else if (t === "text") steps.push({ t: "text", text: "" });
    else if (t === "wait") steps.push({ t: "wait", ms: 100 });
    else steps.push({ t: "scroll", amount: -3 });
    markDirty(true);
    const list = $("steps");
    if (list) list.scrollTop = list.scrollHeight;
  },
  "capture-step": async (el) => {
    const r = await capture();
    if (!r) return;
    Object.assign(S.draft.b.action.steps[+el.dataset.i], { vk: r.vk, mods: r.mods });
    markDirty(true);
  },
  "step-up": (el) => moveStep(+el.dataset.i, -1),
  "step-down": (el) => moveStep(+el.dataset.i, 1),
  "step-del": (el) => { S.draft.b.action.steps.splice(+el.dataset.i, 1); markDirty(true); },
  "set-waits": () => {
    const ms = clamp(parseInt($("wait-all").value, 10) || 0, 0, 600000);
    S.draft.b.action.steps.forEach((s) => { if (s.t === "wait") s.ms = ms; });
    markDirty(true);
  },
  "del-waits": () => { S.draft.b.action.steps = S.draft.b.action.steps.filter((s) => s.t !== "wait"); markDirty(true); },
  "clear-steps": () => { if (confirm("Tüm adımlar silinsin mi?")) { S.draft.b.action.steps = []; markDirty(true); } },
  record: startRecord,
  "save-binding": saveDraft,
  "delete-binding": deleteDraft,
  revert: () => {
    S.dirty = false;
    if (S.draft.isNew) S.draft = { b: newBinding(S.sel.vk), isNew: true };
    else {
      const b = profile().bindings.find((x) => x.id === S.draft.b.id);
      S.draft = b ? { b: clone(b), isNew: false } : null;
    }
    renderPanel();
  },
  "make-default": async () => {
    const cfg = clone(S.config);
    cfg.active_profile = S.view;
    if (await saveConfig(cfg, "Varsayılan profil değişti")) renderAll();
  },
  "profile-settings": profileModal,
  "modal-close": closeModal,
  "pm-add-app": () => {
    const inp = $("pm-app");
    let v = inp.value.trim().toLowerCase().split(/[\\/]/).pop();
    if (!v) return;
    if (!v.includes(".")) v += ".exe";
    modalState.name = $("pm-name").value;
    if (!modalState.apps.includes(v)) modalState.apps.push(v);
    renderProfileModal();
  },
  "pm-add-recent": (el) => {
    modalState.name = $("pm-name").value;
    modalState.apps.push(el.dataset.v);
    renderProfileModal();
  },
  "pm-del-app": (el) => {
    modalState.name = $("pm-name").value;
    modalState.apps.splice(+el.dataset.i, 1);
    renderProfileModal();
  },
  "pm-save": async () => {
    const cfg = clone(S.config);
    const p = cfg.profiles.find((x) => x.id === S.view);
    p.name = $("pm-name").value.trim() || "Profil";
    p.apps = modalState.apps;
    if (await saveConfig(cfg, "Profil kaydedildi")) { closeModal(); renderAll(); }
  },
  "pm-duplicate": async () => {
    const cfg = clone(S.config);
    const src = cfg.profiles.find((x) => x.id === S.view);
    const copy = clone(src);
    copy.id = newId();
    copy.name = `${src.name} (kopya)`.slice(0, 60);
    copy.apps = [];
    copy.bindings.forEach((b) => { b.id = newId(); });
    cfg.profiles.push(copy);
    if (await saveConfig(cfg, "Profil kopyalandı")) {
      closeModal();
      S.view = copy.id;
      S.sel = null;
      S.draft = null;
      renderAll();
    }
  },
  "pm-delete": async () => {
    const p = profile();
    if (!confirm(`"${p.name}" profili ve içindeki ${p.bindings.length} atama silinsin mi?`)) return;
    const cfg = clone(S.config);
    cfg.profiles = cfg.profiles.filter((x) => x.id !== p.id);
    if (cfg.active_profile === p.id) cfg.active_profile = cfg.profiles[0].id;
    if (await saveConfig(cfg, "Profil silindi")) {
      closeModal();
      S.view = S.config.active_profile;
      S.sel = null;
      S.draft = null;
      S.dirty = false;
      renderAll();
    }
  },
  "pm-export": () => {
    const p = profile();
    download(`${p.name.replace(/[^\wçğıöşüÇĞİÖŞÜ -]/g, "") || "profil"}.makro.json`, { makroStudio: 1, profile: { name: p.name, apps: p.apps, bindings: p.bindings } });
  },
  "np-create": async () => {
    const file = $("np-file").files[0];
    let prof;
    if (file) {
      try {
        const data = JSON.parse(await file.text());
        const src = data.profile || data;
        prof = { name: String(src.name || "İçe aktarılan"), apps: Array.isArray(src.apps) ? src.apps : [], bindings: Array.isArray(src.bindings) ? src.bindings : [] };
      } catch (e) {
        return toast("Dosya okunamadı: geçerli bir profil dosyası değil.", "err");
      }
    } else {
      prof = { name: $("np-name").value.trim() || "Yeni profil", apps: [], bindings: [] };
    }
    prof.id = newId();
    prof.bindings.forEach((b) => { b.id = newId(); });
    const cfg = clone(S.config);
    cfg.profiles.push(prof);
    if (await saveConfig(cfg, file ? "Profil içe aktarıldı" : "Profil oluşturuldu")) {
      closeModal();
      S.view = prof.id;
      S.sel = null;
      S.draft = null;
      renderAll();
    }
  },
  "set-hotkey": async () => {
    const r = await capture();
    if (!r) return;
    if (r.vk <= 6) return toast("Kısayol bir klavye tuşu olmalı.", "err");
    const cfg = clone(S.config);
    cfg.toggle_hotkey = r;
    if (await saveConfig(cfg, "Kısayol değişti")) { settingsModal(); renderAll(); }
  },
  quit: async () => {
    if (!confirm("Makro Studio tamamen kapatılsın mı? Makrolar çalışmayı durdurur.")) return;
    await cmd("quit").catch(() => {});
    document.body.innerHTML = `<div class="offline" style="inset:0"><div><h2>Makro Studio kapatıldı</h2><p>Bu pencereyi kapatabilirsin.</p></div></div>`;
  },
};

function moveStep(i, dir) {
  const steps = S.draft.b.action.steps;
  const j = i + dir;
  if (j < 0 || j >= steps.length) return;
  [steps[i], steps[j]] = [steps[j], steps[i]];
  markDirty(true);
}

document.addEventListener("click", (ev) => {
  const el = ev.target.closest("[data-act]");
  if (!el || el.tagName === "INPUT") return;
  const h = handlers[el.dataset.act];
  if (h) h(el, ev);
});

document.addEventListener("change", async (ev) => {
  const el = ev.target;
  if (el.dataset.act === "toggle-binding") {
    const cfg = clone(S.config);
    const b = cfg.profiles.find((x) => x.id === S.view).bindings.find((x) => x.id === el.dataset.id);
    b.enabled = el.checked;
    if (await saveConfig(cfg)) {
      if (S.draft && !S.draft.isNew && S.draft.b.id === b.id && !S.dirty) S.draft.b.enabled = b.enabled;
      renderAll();
    } else el.checked = !el.checked;
    return;
  }
  if (el.dataset.setting === "auto_switch") {
    const cfg = clone(S.config);
    cfg.auto_switch = el.checked;
    if (!(await saveConfig(cfg))) el.checked = !el.checked;
    return;
  }
  if (el.dataset.setting === "autostart") {
    try {
      const r = await cmd("autostart", { value: el.checked });
      S.autostart = r.autostart;
      el.checked = r.autostart;
    } catch (e) {
      toast(e.message, "err");
      el.checked = !el.checked;
    }
    return;
  }
  if (el.id === "rec-mouse") S.recordMouse = el.checked;
});

document.addEventListener("input", (ev) => {
  const el = ev.target;
  if (!S.draft) return;
  const b = S.draft.b;
  if (el.dataset.bind) {
    let v = el.type === "checkbox" ? el.checked : el.value;
    if (el.dataset.num) {
      const [lo, hi] = el.dataset.num.split(",").map(Number);
      v = clamp(parseInt(v, 10) || lo, lo, hi);
    }
    setPath(b, el.dataset.bind, v);
    markDirty(el.type === "checkbox");
  } else if (el.dataset.rate) {
    const v = clamp(parseInt(el.value, 10) || 1, 1, 1000);
    b.action[el.dataset.rate] = v;
    // Kaydırıcı ve sayı kutusu birbirini izlesin
    document.querySelectorAll(`[data-rate="${el.dataset.rate}"]`).forEach((x) => { if (x !== el) x.value = v; });
    markDirty();
  } else if (el.dataset.step) {
    const s = b.action.steps[+el.dataset.step];
    const f = el.dataset.field;
    if (f === "ms") s.ms = clamp(parseInt(el.value, 10) || 0, 0, 600000);
    else if (f === "amount") s.amount = clamp(parseInt(el.value, 10) || 0, -100, 100);
    else s[f] = el.value;
    markDirty();
  }
});

document.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape" && !$("modal").hidden) closeModal();
  if (ev.key === "Enter" && ev.target.id === "pm-app") handlers["pm-add-app"]();
  if (ev.key === "s" && ev.ctrlKey && S.draft) { ev.preventDefault(); saveDraft(); }
});
$("modal").addEventListener("mousedown", (ev) => { if (ev.target === $("modal")) closeModal(); });
$("master").addEventListener("click", () => cmd("enabled", { value: S.status.enabled === false }).catch((e) => toast(e.message, "err")));
$("stop-all").addEventListener("click", () => cmd("stop_all").then(() => toast("Tüm makrolar durduruldu", "ok")).catch((e) => toast(e.message, "err")));
$("open-settings").addEventListener("click", settingsModal);
$("add-profile").addEventListener("click", addProfileModal);
$("capture-cancel").addEventListener("click", () => { cmd("capture", { value: false }).catch(() => {}); finishCapture(null); });
$("rec-stop").addEventListener("click", stopRecord);
new ResizeObserver(fitKeyboard).observe($("kb-wrap"));
// Fare yan tuşları pencerede "geri/ileri" yapmasın
window.addEventListener("mouseup", (ev) => { if (ev.button === 3 || ev.button === 4) ev.preventDefault(); });

// --- Canlı bağlantı ---
function connect() {
  const es = new EventSource(`/api/events?t=${encodeURIComponent(TOKEN)}`);
  let offlineTimer = null;
  es.addEventListener("open", () => {
    clearTimeout(offlineTimer);
    if (!S.online) {
      S.online = true;
      document.querySelector(".offline")?.remove();
      load();
    }
  });
  es.addEventListener("error", () => {
    clearTimeout(offlineTimer);
    offlineTimer = setTimeout(() => {
      if (S.online && es.readyState !== EventSource.OPEN) {
        S.online = false;
        const el = document.createElement("div");
        el.className = "offline";
        el.innerHTML = "<div><h2>Bağlantı yok</h2><p>Makro Studio kapalı görünüyor. Yeniden açınca bu pencere kendiliğinden bağlanır.</p></div>";
        document.body.appendChild(el);
      }
    }, 2500);
  });
  es.addEventListener("status", (ev) => {
    const st = JSON.parse(ev.data);
    if (st.exe && !IGNORED_EXES.has(st.exe) && S.recentExes[0] !== st.exe) {
      S.recentExes = [st.exe, ...S.recentExes.filter((e) => e !== st.exe)].slice(0, 8);
    }
    S.status = st;
    if (S.config) renderLive();
  });
  es.addEventListener("captured", (ev) => finishCapture(JSON.parse(ev.data)));
  es.addEventListener("recorded", (ev) => onRecorded(JSON.parse(ev.data)));
  es.addEventListener("engine_error", (ev) => toast(`Motor hatası: ${JSON.parse(ev.data)}`, "err"));
}

async function load() {
  try {
    const st = await api("/api/state");
    S.config = st.config;
    S.status = st.status;
    S.keys = st.keys;
    S.scanMap = st.scan_map;
    S.autostart = st.autostart;
    S.version = st.version;
    if (!S.config.profiles.some((p) => p.id === S.view)) S.view = S.config.active_profile;
    if (S.sel && !S.dirty) {
      const b = profile().bindings.find((x) => x.id === S.sel.bid);
      S.draft = b ? { b: clone(b), isNew: false } : S.draft;
    }
    fitKeyboard();
    renderAll();
  } catch (e) {
    document.body.innerHTML = `<div class="offline" style="inset:0"><div><h2>Açılamadı</h2><p>${esc(e.message)}<br>Makro Studio'yu tepsi ikonundan yeniden aç.</p></div></div>`;
  }
}

load().then(connect);
