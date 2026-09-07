const $ = (sel, el = document) => el.querySelector(sel);
const app = $("#app");
const toastEl = $("#toast");
let me = null;
let csrf = null;
let catalog = { trunks: [], branches: [] };
let draft = null;
let currentTrunk = "T01";
let openBranch = null;
let branchLeaves = {};
let simpleMode = true;
let treeCollapsed = false;
let fruitOpen = null;
const cautionAck = new Set();
const FRUIT_POS = [
  [18, 22], [38, 10], [58, 16], [74, 28], [22, 48], [48, 36],
  [70, 50], [30, 18], [54, 8], [12, 40], [80, 40], [42, 24],
];

function toast(msg) {
  toastEl.hidden = false;
  toastEl.textContent = msg;
  setTimeout(() => { toastEl.hidden = true; }, 2800);
}

async function api(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  const token = csrfToken();
  if (token && opts.method && opts.method !== "GET") headers["X-CSRF-Token"] = token;
  if (opts.json) {
    headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(opts.json);
    delete opts.json;
  }
  const res = await fetch(path, { credentials: "include", ...opts, headers });
  const ct = res.headers.get("content-type") || "";
  const data = ct.includes("json") ? await res.json() : null;
  if (!res.ok) {
    const detail = data && data.detail;
    const code = (data && data.error) || (detail && detail.error) || (typeof detail === "string" ? detail : "") || res.statusText;
    const err = new Error(code);
    err.status = res.status;
    err.data = { ...(data || {}), error: (data && data.error) || (typeof detail === "string" ? detail : data?.detail?.error) };
    err.data.missing_trunks = data?.missing_trunks || data?.detail?.missing_trunks;
    throw err;
  }
  return data;
}

function csrfToken() {
  const part = document.cookie.split("; ").find((x) => x.startsWith("tof_csrf="));
  if (part) return decodeURIComponent(part.slice("tof_csrf=".length));
  return csrf || "";
}

function hash() {
  return (location.hash || "#landing").replace("#", "").split("/")[0];
}

function navShow(show) {
  $("#top-nav").hidden = !show;
  document.querySelectorAll("[data-nav]").forEach((a) => {
    a.classList.toggle("active", a.dataset.nav === hash());
  });
}

async function refreshMe() {
  try {
    me = await api("api/v1/me");
    csrf = me.csrf;
    return me;
  } catch {
    me = null;
    csrf = null;
    return null;
  }
}

function landing() {
  navShow(false);
  app.innerHTML = `
    <section class="hero stack">
      <h1>人生の経験が、一本の木になる</h1>
      <p>幹・枝・葉から経験を選ぶと、選ぶたびに木が育ちます。完成した木を通じて、近い境遇の人と安全につながれます。18歳以上限定です。</p>
      <p class="muted">選択内容は原則非公開です。木は診断や人格評価ではありません。医療・法律・緊急支援の代替ではありません。</p>
      <form id="demo-form" class="stack">
        <label>開発用デモログイン（メール）
          <input name="email" type="email" value="you@local.test" required />
        </label>
        <div class="row">
          <button class="btn" type="submit">デモで始める</button>
          <button class="btn secondary" type="button" id="magic">マジックリンクを送る</button>
          ${me && me.google_enabled ? `<a class="btn secondary" href="/api/v1/auth/google/start">Googleで続ける</a>` : ""}
        </div>
      </form>
    </section>`;
  $("#demo-form").onsubmit = async (e) => {
    e.preventDefault();
    const email = new FormData(e.target).get("email");
    await api("/api/v1/auth/demo", { method: "POST", json: { email } });
    await refreshMe();
    location.hash = me.age_verified ? (me.has_published_tree ? "#tree" : "#tree") : "#age";
    route();
  };
  $("#magic").onclick = async () => {
    const email = $("[name=email]").value;
    const r = await api("/api/v1/auth/magic-link", { method: "POST", json: { email } });
    if (r.dev_link) location.href = r.dev_link;
    else toast("メールを確認してください");
  };
}

function ageView() {
  navShow(false);
  app.innerHTML = `
    <section class="panel stack">
      <h1>年齢確認と同意</h1>
      <p>本サービスは18歳以上の方だけが利用できます。利用規約とプライバシーの考え方に同意してください。</p>
      <ul class="muted">
        <li>同じ境遇であることを運営は保証しません。</li>
        <li>助言の正確性は保証しません。</li>
        <li>出会い目的、差別、個人情報の晒し、自傷の助長は禁止です。</li>
      </ul>
      <form id="age-form" class="stack">
        <label>生年月日
          <input name="birthdate" type="date" />
        </label>
        <label class="row"><input type="checkbox" name="confirm" /> 私は18歳以上です</label>
        <label class="row"><input type="checkbox" name="terms" required /> 規約とプライバシーに同意します</label>
        <button class="btn">続ける</button>
      </form>
    </section>`;
  $("#age-form").onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    try {
      if (fd.get("confirm")) await api("/api/v1/me/age-verify", { method: "POST", json: { confirm_18: true } });
      else await api("/api/v1/me/age-verify", { method: "POST", json: { birthdate: fd.get("birthdate") } });
      location.hash = "#profile";
      route();
    } catch (err) {
      toast(err.status === 403 ? "18歳未満の方は利用できません" : "確認できませんでした");
    }
  };
}

function profileView() {
  navShow(true);
  const p = me.profile || {};
  app.innerHTML = `
    <section class="panel stack">
      <h1>プロフィール</h1>
      <form id="pf" class="stack">
        <label>呼び名 <input name="display_name" maxlength="40" value="${escapeHtml(p.display_name || "")}" required /></label>
        <label>自己紹介 <textarea name="blurb" maxlength="400">${escapeHtml(p.blurb || "")}</textarea></label>
        <label>自己紹介の公開
          <select name="blurb_visibility">
            <option value="public">発見画面でも表示</option>
            <option value="friends">友達にだけ表示</option>
            <option value="hidden">表示しない</option>
          </select>
        </label>
        <button class="btn">保存してはじめる</button>
      </form>
    </section>`;
  $("[name=blurb_visibility]").value = p.blurb_visibility || "friends";
  $("#pf").onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    await api("/api/v1/me/profile", { method: "PUT", json: Object.fromEntries(fd) });
    location.hash = "#tree";
    route();
  };
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

async function loadCatalog() {
  catalog = await api("/api/v1/catalog");
}

async function loadDraft() {
  draft = await api("/api/v1/me/tree-draft");
}

async function loadLeaves(branchId) {
  if (branchLeaves[branchId]) return branchLeaves[branchId];
  const data = await api(`/api/v1/catalog?branch_id=${encodeURIComponent(branchId)}`);
  branchLeaves[branchId] = data.leaves;
  return data.leaves;
}

function selectedSet() {
  return new Set(draft.leaf_ids || []);
}

async function saveSelections(ids) {
  const next = await api("/api/v1/me/tree-draft/selections", { method: "PUT", json: { leaf_ids: ids } });
  draft = { ...draft, ...next };
  renderTreeSvg();
  renderTrunks();
}

function localCanPublish() {
  const ids = draft?.leaf_ids || [];
  const trunks = catalog.trunks || [];
  if (!trunks.length) return Boolean(draft?.can_publish);
  return trunks.every((t) => ids.some((id) => id === t.id || id.startsWith(`${t.id}-`)));
}

function grownCount() {
  const ids = draft?.leaf_ids || [];
  return (catalog.trunks || []).filter((t) => ids.some((id) => id === t.id || id.startsWith(`${t.id}-`))).length;
}

function renderTreeSvg() {
  const canvas = $("#tree-canvas");
  if (!canvas || !draft) return;
  const wrap = $("#tree-svg");
  wrap.innerHTML = draft.svg || "";
  const svg = wrap.querySelector("svg");
  if (svg) {
    svg.classList.remove("pulse");
    void svg.offsetWidth;
    svg.classList.add("pulse");
  }
  const status = $("#tree-status");
  if (status) {
    const n = grownCount();
    const total = (catalog.trunks || []).length || 5;
    status.textContent = n >= total
      ? "5つの幹がそろいました。この木を完成できます"
      : `中央の木：${n} / ${total} の幹が伸びています。葉を選ぶと枝が育ちます`;
  }
  const pub = $("#publish-tree");
  if (pub) {
    const ok = Boolean(draft.can_publish) || localCanPublish();
    pub.hidden = !ok;
    pub.disabled = !ok;
  }
}

function renderTrunks() {
  const host = $("#trunks");
  if (!host || !draft) return;
  host.innerHTML = catalog.trunks.map((t, i) => {
    const p = (draft.progress && draft.progress[t.id]) || { count: 0, complete: false };
    const localOn = (draft.leaf_ids || []).some((id) => id === t.id || id.startsWith(`${t.id}-`));
    const done = p.complete || localOn;
    const count = Math.max(p.count || 0, (draft.leaf_ids || []).filter((id) => id === t.id || id.startsWith(`${t.id}-`)).length);
    return `
      ${i ? '<div class="life-line"></div>' : ""}
      <button class="trunk-node" data-trunk="${t.id}" ${currentTrunk === t.id ? 'aria-current="true"' : ""}>
        <span class="dot ${done ? "done" : ""}">${done ? "✓" : count}</span>
        <span><strong>${escapeHtml(t.label_ja)}</strong><br /><span class="muted">${done ? "1つ以上選択済み" : "未完了"} · ${count}葉</span></span>
      </button>`;
  }).join("");
  host.querySelectorAll("[data-trunk]").forEach((btn) => {
    btn.onclick = () => { currentTrunk = btn.dataset.trunk; openBranch = null; renderSelect(); renderTrunks(); };
  });
}

function branchesOf(trunkId) {
  return catalog.branches.filter((b) => b.trunk_id === trunkId);
}

async function renderSelect() {
  const pane = $("#select-pane");
  if (!pane) return;
  const trunk = catalog.trunks.find((t) => t.id === currentTrunk);
  const selected = selectedSet();
  const branches = branchesOf(currentTrunk);
  const complete = Boolean(draft.progress?.[currentTrunk]?.complete) || (draft.leaf_ids || []).some((id) => id === currentTrunk || id.startsWith(`${currentTrunk}-`));
  if (simpleMode && !openBranch && branches[0]) openBranch = branches[0].id;
  pane.innerHTML = `
    <div>
      <h2>${escapeHtml(trunk.label_ja)}</h2>
      <p class="muted">${simpleMode ? "最初の木をつくる：枝を開き、自分に近い葉を1つ以上選びます。追加選択は任意です。" : "詳細編集。検索と絞り込みが使えます。"}</p>
    </div>
    ${simpleMode ? "" : `
      <input id="leaf-search" placeholder="枝を横断して検索" />
      <label class="row"><input type="checkbox" id="only-selected" /> 選択済みだけ</label>
      <div id="search-hits"></div>`}
    <div id="branch-list"></div>
    <div class="sticky-next row">
      ${complete && simpleMode ? `<button class="btn" id="next-trunk">次の幹へ</button>` : ""}
      ${(draft.can_publish || localCanPublish()) ? `<button class="btn" id="publish">この木を完成させる</button>` : `<span class="muted">5つの幹で1葉以上選ぶと完成できます（いま ${grownCount()} / ${(catalog.trunks || []).length || 5}）</span>`}
    </div>`;
  const list = $("#branch-list");
  list.innerHTML = branches.map((b) => {
    const count = [...selected].filter((id) => id === b.id || id.startsWith(`${b.id}-`)).length;
    return `<div>
      <button class="accordion" data-branch="${b.id}" aria-expanded="${openBranch === b.id}">${openBranch === b.id ? "▲" : "▼"} ${escapeHtml(b.label_ja)} ${count ? `· 選択 ${count}` : ""}</button>
      <div class="chips" id="leaves-${b.id}"></div>
    </div>`;
  }).join("");
  list.querySelectorAll(".accordion").forEach((btn) => {
    btn.onclick = async () => {
      openBranch = openBranch === btn.dataset.branch ? null : btn.dataset.branch;
      await renderSelect();
    };
  });
  if (openBranch) await renderLeaves(openBranch);
  const next = $("#next-trunk");
  if (next) next.onclick = () => {
    const idx = catalog.trunks.findIndex((t) => t.id === currentTrunk);
    currentTrunk = catalog.trunks[Math.min(idx + 1, catalog.trunks.length - 1)].id;
    openBranch = null;
    renderTrunks();
    renderSelect();
  };
  const pub = $("#publish");
  if (pub) pub.onclick = publishTree;
  const search = $("#leaf-search");
  if (search) {
    search.oninput = debounce(async () => {
      const q = search.value.trim();
      if (!q) { $("#search-hits").innerHTML = ""; return; }
      const r = await api(`/api/v1/catalog/search?q=${encodeURIComponent(q)}`);
      const only = $("#only-selected")?.checked;
      const items = r.items.filter((it) => !only || selected.has(it.id));
      $("#search-hits").innerHTML = items.map((it) => `<button type="button" class="leaf-chip ${selected.has(it.id) ? "is-selected" : ""}" data-sid="${it.id}" aria-pressed="${selected.has(it.id)}"><span class="leaf-check">${selected.has(it.id) ? "✓" : ""}</span><span class="leaf-label">${escapeHtml(it.label_short_ja)}</span></button>`).join("");
      $("#search-hits").querySelectorAll("[data-sid]").forEach((b) => b.onclick = () => toggleLeaf(b.dataset.sid, null, b));
    }, 200);
  }
}

async function renderLeaves(branchId) {
  const host = $(`#leaves-${branchId}`);
  if (!host) return;
  const leaves = await loadLeaves(branchId);
  const selected = selectedSet();
  host.innerHTML = leaves.map((leaf) => {
    const long = leaf.label_short_ja.length > 12;
    const on = selected.has(leaf.id);
    return `<button type="button" class="leaf-chip ${long ? "cardish" : ""} ${on ? "is-selected" : ""}" data-leaf="${leaf.id}" aria-pressed="${on}">
      <span class="leaf-check" aria-hidden="true">${on ? "✓" : ""}</span>
      <span class="leaf-label">${escapeHtml(leaf.label_short_ja)}</span>
      <span class="leaf-more muted" data-more="${leaf.id}">詳しく見る</span>
    </button>`;
  }).join("");
  host.querySelectorAll("[data-leaf]").forEach((btn) => {
    btn.onclick = (e) => {
      const more = e.target.closest && e.target.closest("[data-more]");
      if (more) {
        e.preventDefault();
        e.stopPropagation();
        const leaf = leaves.find((l) => l.id === more.getAttribute("data-more"));
        if (leaf) alert(leaf.description_ja);
        return;
      }
      toggleLeaf(btn.dataset.leaf, leaves, btn);
    };
  });
}

async function toggleLeaf(id, leaves, chip) {
  const leaf = (leaves || []).find((l) => l.id === id) || (await findLeaf(id));
  if (leaf?.sensitivity === "caution" && !cautionAck.has(id) && !selectedSet().has(id)) {
    const ok = confirm("この項目は注意して扱います。刺激の強い内容を含む場合があります。続けますか？");
    if (!ok) return;
    cautionAck.add(id);
  }
  const next = selectedSet();
  if (next.has(id)) {
    if (next.size > 40 && !confirm("選択を解除しますか？")) return;
    next.delete(id);
  } else next.add(id);
  markChip(chip, next.has(id));
  const canvas = $(".tree-svg");
  canvas?.classList.add("pulse");
  try {
    await saveSelections([...next]);
  } catch (err) {
    toast(err.data?.error === "csrf" ? "もう一度ログインしてください" : "選択を保存できませんでした");
    return;
  }
  await renderSelect();
}

function markChip(chip, on) {
  if (!chip) return;
  chip.setAttribute("aria-pressed", on ? "true" : "false");
  chip.classList.toggle("is-selected", on);
  const check = chip.querySelector(".leaf-check");
  if (check) check.textContent = on ? "✓" : "";
}

async function findLeaf(id) {
  const branch = id.split("-").slice(0, 2).join("-");
  const leaves = await loadLeaves(branch);
  return leaves.find((l) => l.id === id);
}

async function publishTree() {
  try {
    await api("/api/v1/me/tree-draft/publish", { method: "POST", json: {} });
    simpleMode = false;
    toast("最初の木が完成しました。経験はあとから追加できます");
    await refreshMe();
    await loadDraft();
    renderTreeSvg();
    renderTrunks();
    await renderSelect();
    if (me.has_published_tree) loadFruits(me.id);
  } catch (err) {
    const missing = err.data?.missing_trunks;
    if (missing?.length) toast("まだ未完了の幹があります。各幹で葉を1つ以上選んでください");
    else if (err.data?.error === "csrf") toast("もう一度ログインしてください");
    else toast("完成できませんでした。各幹で葉が選ばれているか確認してください");
  }
}

async function treeView() {
  navShow(true);
  if (!me.age_verified) { location.hash = "#age"; return route(); }
  await loadCatalog();
  await loadDraft();
  if (!me.profile?.display_name) { location.hash = "#profile"; return route(); }
  if (me.has_published_tree) simpleMode = false;
  app.innerHTML = `
    <div class="row" style="margin-bottom:12px">
      <button class="btn secondary" id="toggle-tree">${treeCollapsed ? "木を表示" : "木を折りたたむ"}</button>
      <button class="btn secondary" id="mode">${simpleMode ? "詳細編集へ" : "簡易モードへ"}</button>
      ${me.has_published_tree ? `<a class="btn secondary" href="#decorate">思い出の画像を飾る</a>
        <a class="btn secondary" href="#routes">自由ルート</a>` : ""}
      ${me.growth ? `<span class="muted">いまの段階：${escapeHtml(me.growth.name)}</span>` : ""}
    </div>
    <section class="workspace">
      <aside class="panel" style="padding:16px"><div class="trunk-list" id="trunks"></div></aside>
      <div class="tree-stage">
        <div class="tree-canvas ${treeCollapsed ? "collapsed" : ""}" id="tree-canvas">
          <div id="tree-svg"></div>
          <div class="fruits" id="fruits"></div>
        </div>
        <p class="tree-status" id="tree-status"></p>
        <button class="btn" id="publish-tree" hidden>この木を完成させる</button>
      </div>
      <aside class="select-pane" id="select-pane"></aside>
    </section>`;
  $("#toggle-tree").onclick = () => { treeCollapsed = !treeCollapsed; treeView(); };
  $("#mode").onclick = () => { simpleMode = !simpleMode; treeView(); };
  $("#publish-tree").onclick = publishTree;
  renderTrunks();
  renderTreeSvg();
  await renderSelect();
  if (me.has_published_tree) loadFruits(me.id);
}

async function loadFruits(userId) {
  const host = $("#fruits");
  if (!host) return;
  const r = await api(`/api/v1/trees/${userId}/decorations`);
  host.innerHTML = r.items.map((it, i) => {
    const [x, y] = FRUIT_POS[i % FRUIT_POS.length];
    const overlap = i > 6 ? i % 3 * 8 : 0;
    return `<img class="fruit" data-fid="${it.id}" src="${it.thumb_url}" alt="" style="left:${x + overlap * 0.3}%; top:${y}%" tabindex="0" />`;
  }).join("") + (fruitOpen ? fruitCardHtml(r.items.find((x) => x.id === fruitOpen)) : "");
  host.querySelectorAll(".fruit").forEach((el) => {
    const open = () => { fruitOpen = Number(el.dataset.fid); loadFruits(userId); };
    const close = () => { fruitOpen = null; loadFruits(userId); };
    el.onmouseenter = open;
    el.onmouseleave = (e) => { if (!e.relatedTarget?.closest?.(".fruit-card")) close(); };
    el.onfocus = open;
    el.onclick = (e) => { e.preventDefault(); fruitOpen = fruitOpen === Number(el.dataset.fid) ? null : Number(el.dataset.fid); loadFruits(userId); };
  });
  document.onkeydown = (e) => { if (e.key === "Escape") { fruitOpen = null; loadFruits(userId); } };
}

function fruitCardHtml(it) {
  if (!it) return "";
  return `<div class="fruit-card" style="left:30%; top:30%">
    <img src="${it.thumb_url}" alt="" />
    <p class="muted">${escapeHtml(it.created_at.slice(0, 16))}</p>
    <p>${escapeHtml(it.caption || "")}</p>
    <a href="#timeline">元の投稿へ</a>
  </div>`;
}

async function timelineView() {
  navShow(true);
  if (!me.sns_ready) return locked();
  const tabs = await api("/api/v1/timelines");
  app.innerHTML = `
    <section class="stack">
      <h1>タイムライン</h1>
      <p class="notice">個人情報を書かないでください。診断や治療を断定しないでください。同じ葉を選んだ人だけが見られます。</p>
      <div class="tabs" id="ttabs">${tabs.tabs.map((t, i) => `<button class="chip tab" data-i="${i}">${escapeHtml(t.label_short_ja)}</button>`).join("") || "<p class=muted>選択した葉がありません</p>"}</div>
      <div id="tcontent"></div>
    </section>`;
  const open = async (i) => {
    const tab = tabs.tabs[i];
    if (!tab) return;
    document.querySelectorAll(".tab").forEach((el, idx) => el.setAttribute("aria-pressed", idx === i));
    const path = tab.type === "custom" ? `/api/v1/custom-timelines/${tab.origin_route_id}/posts` : `/api/v1/timelines/${tab.leaf_id}/posts`;
    const data = await api(path);
    $("#tcontent").innerHTML = `
      <form class="card stack" id="post-form">
        <textarea name="body" maxlength="2000" required placeholder="いまの気持ちや経験を書く"></textarea>
        ${tab.type === "leaf" ? `<input type="file" name="images" accept="image/jpeg,image/png,image/webp" multiple />` : ""}
        <button class="btn">投稿する</button>
      </form>
      <div id="posts">${data.items.map(postHtml).join("") || "<p class=muted>まだ投稿がありません</p>"}</div>`;
    $("#post-form").onsubmit = async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const res = await fetch(path, { method: "POST", body: fd, credentials: "include", headers: { "X-CSRF-Token": csrf } });
      const js = await res.json();
      if (js.helpline) showHelp(js.helpline);
      open(i);
    };
    bindPosts();
  };
  document.querySelectorAll(".tab").forEach((el) => el.onclick = () => open(Number(el.dataset.i)));
  if (tabs.tabs[0]) open(0);
}

function postHtml(p) {
  return `<article class="card post" data-pid="${p.id}">
    <p><strong>${escapeHtml(p.author?.display_name || "")}</strong> <span class="muted">${escapeHtml(p.created_at.slice(0, 16))}</span></p>
    ${p.author?.tree_url ? `<div>${p.author.tree_url.endsWith("svg") ? "" : ""}</div>` : ""}
    <p>${escapeHtml(p.body)}</p>
    <div class="row">${(p.images || []).map((im) => `<img src="${im.thumb_url}" alt="" width="120" />`).join("")}</div>
    <div class="row">
      ${p.can_react ? `<button class="btn secondary" data-react="post:${p.id}" aria-pressed="${p.reacted}">共感</button>` : ""}
      <button class="btn ghost" data-friend="${p.author?.id}">友達申請</button>
      <button class="btn ghost" data-report="post:${p.id}">通報</button>
    </div>
    <div>${(p.comments || []).map((c) => `<p><strong>${escapeHtml(c.author?.display_name || "")}</strong> ${escapeHtml(c.body)}</p>`).join("")}</div>
    <form data-cmt="${p.id}" class="row"><input name="body" maxlength="1000" required /><button class="btn secondary">コメント</button></form>
  </article>`;
}

function bindPosts() {
  document.querySelectorAll("[data-react]").forEach((b) => {
    b.onclick = async () => {
      const [type, id] = b.dataset.react.split(":");
      if (b.getAttribute("aria-pressed") === "true") await api(`/api/v1/reactions/${type}/${id}`, { method: "DELETE" });
      else await api(`/api/v1/reactions/${type}/${id}`, { method: "PUT", json: {} });
      toast("更新しました");
    };
  });
  document.querySelectorAll("[data-cmt]").forEach((f) => {
    f.onsubmit = async (e) => {
      e.preventDefault();
      const r = await api(`/api/v1/posts/${f.dataset.cmt}/comments`, { method: "POST", json: { body: f.body.value } });
      if (r.helpline) showHelp(r.helpline);
      toast("コメントしました");
    };
  });
  document.querySelectorAll("[data-friend]").forEach((b) => b.onclick = () => sendFriend(Number(b.dataset.friend)));
  document.querySelectorAll("[data-report]").forEach((b) => b.onclick = () => report(...b.dataset.report.split(":")));
}

function showHelp(h) {
  toast(`${h.label}：地域の公的窓口と、緊急時は緊急通報を`);
}

function locked() {
  app.innerHTML = `<section class="panel"><h1>木が完成すると使えます</h1><p>発見・友達・タイムラインは、5つの幹を完成させたあと利用できます。</p><a class="btn" href="#tree">木をつくる</a></section>`;
}

async function discoverView() {
  navShow(true);
  if (!me.sns_ready) return locked();
  const data = await api("/api/v1/discovery");
  app.innerHTML = `<section class="stack"><h1>近い木</h1>
    <div class="grid-cards">${data.items.map((it) => `
      <article class="card tree-card">
        <img src="${it.tree_url}" alt="${escapeHtml(it.display_name)}さんの人生の木" />
        <h2>${escapeHtml(it.display_name)}</h2>
        <p class="muted">${escapeHtml(it.resonance)}</p>
        <p>${escapeHtml(it.blurb || "")}</p>
        <div class="row">
          <button class="btn" data-friend="${it.id}">申請</button>
          <button class="btn secondary" data-react="tree:${it.id}">共感</button>
          <button class="btn ghost" data-block="${it.id}">ブロック</button>
          <button class="btn ghost" data-report="tree:${it.id}">通報</button>
        </div>
      </article>`).join("") || `<p class="muted">今は近い木が見つかりません。タイムラインで話してみるか、後日また探してください。条件は自動では広げません。</p>`}
    </div></section>`;
  bindSocial();
}

function bindSocial() {
  document.querySelectorAll("[data-friend]").forEach((b) => b.onclick = () => sendFriend(Number(b.dataset.friend)));
  document.querySelectorAll("[data-block]").forEach((b) => b.onclick = async () => {
    await api(`/api/v1/blocks/${b.dataset.block}`, { method: "POST", json: {} });
    toast("ブロックしました");
    route();
  });
  document.querySelectorAll("[data-report]").forEach((b) => b.onclick = () => report(...b.dataset.report.split(":")));
  document.querySelectorAll("[data-react]").forEach((b) => b.onclick = async () => {
    const [type, id] = b.dataset.react.split(":");
    await api(`/api/v1/reactions/${type}/${id}`, { method: "PUT", json: {} });
    toast("共感しました");
  });
}

async function sendFriend(id) {
  const message = prompt("ひとこと（任意・要素名は入れません）", "") || "";
  await api("/api/v1/connections", { method: "POST", json: { user_id: id, message } });
  toast("申請しました");
}

async function report(type, id) {
  const reason = prompt("理由: harassment / discrimination / pii / solicitation / harm / medical / sexual / other", "other");
  const detail = prompt("詳細（任意）", "") || "";
  const r = await api("/api/v1/reports", { method: "POST", json: { target_type: type, target_id: id, reason, detail } });
  toast(`受付 ${r.ticket}`);
}

async function friendsView() {
  navShow(true);
  if (!me.sns_ready) return locked();
  const data = await api("/api/v1/friends");
  app.innerHTML = `<section class="stack">
    <h1>友達</h1>
    <h2>届いた申請</h2>
    ${data.incoming.map((r) => `<div class="card row"><span>${escapeHtml(r.from.display_name)}：${escapeHtml(r.message)}</span>
      <button class="btn" data-act="accept:${r.id}">承認</button>
      <button class="btn secondary" data-act="decline:${r.id}">拒否</button></div>`).join("") || "<p class=muted>なし</p>"}
    <h2>送った申請</h2>
    ${data.outgoing.map((r) => `<div class="card row"><span>${escapeHtml(r.to.display_name)}</span>
      <button class="btn secondary" data-act="cancel:${r.id}">取消</button></div>`).join("") || "<p class=muted>なし</p>"}
    <h2>友達一覧</h2>
    ${data.friends.map((f) => `<div class="card row">
      <img src="${f.tree_url}" alt="${escapeHtml(f.display_name)}さんの人生の木" width="80" />
      <div><strong>${escapeHtml(f.display_name)}</strong><p>${escapeHtml(f.blurb || "")}</p></div>
      <a class="btn" href="#messages/${f.id}">メッセージ</a>
      <button class="btn secondary" data-un="${f.id}">解除</button>
    </div>`).join("") || "<p class=muted>まだいません</p>"}
  </section>`;
  document.querySelectorAll("[data-act]").forEach((b) => b.onclick = async () => {
    const [action, id] = b.dataset.act.split(":");
    await api(`/api/v1/connections/${id}`, { method: "PATCH", json: { action } });
    friendsView();
  });
  document.querySelectorAll("[data-un]").forEach((b) => b.onclick = async () => {
    await api(`/api/v1/friends/${b.dataset.un}`, { method: "DELETE" });
    friendsView();
  });
}

async function messagesView() {
  navShow(true);
  const id = Number((location.hash.split("/")[1] || "0"));
  if (!id) { app.innerHTML = `<p>友達一覧から会話を開いてください。</p>`; return; }
  const data = await api(`/api/v1/messages/${id}`);
  app.innerHTML = `<section class="panel stack">
    <h1>メッセージ</h1>
    <div id="msgs">${data.items.map((m) => `<p><strong>${m.sender_id === me.id ? "自分" : "相手"}</strong> ${escapeHtml(m.body)}</p>`).join("")}</div>
    <form id="mf" class="stack"><textarea name="body" required maxlength="2000"></textarea>
      <div class="row"><button class="btn">送る</button>
      <button type="button" class="btn ghost" id="rep">通報</button>
      <button type="button" class="btn ghost" id="blk">ブロック</button></div>
    </form>
  </section>`;
  $("#mf").onsubmit = async (e) => {
    e.preventDefault();
    const r = await api(`/api/v1/messages/${id}`, { method: "POST", json: { body: e.target.body.value } });
    if (r.helpline) showHelp(r.helpline);
    messagesView();
  };
  $("#rep").onclick = () => report("message", id);
  $("#blk").onclick = async () => { await api(`/api/v1/blocks/${id}`, { method: "POST", json: {} }); toast("ブロックしました"); };
}

async function routesView() {
  navShow(true);
  if (!me.sns_ready) return locked();
  const mine = await api("/api/v1/me/custom-routes");
  const found = await api("/api/v1/custom-routes/search?q=");
  app.innerHTML = `<section class="stack">
    <h1>自由ルート</h1>
    <p class="muted">固定5幹の完成の代わりにはなりません。公開前に安全検査があります。</p>
    <form id="rf" class="card stack">
      <label>幹 <input name="trunk_text" maxlength="40" required /></label>
      <label>枝 <input name="branch_text" maxlength="60" required /></label>
      <label>葉 <input name="leaf_text" maxlength="120" required /></label>
      <button class="btn">作成して検査</button>
    </form>
    <h2>自分のルート</h2>
    ${mine.items.map((r) => `<div class="card"><strong>${escapeHtml(r.leaf_text)}</strong> <span class="muted">${escapeHtml(r.status)}${r.reason ? " · " + r.reason : ""}</span></div>`).join("")}
    <h2>公開されている原典</h2>
    <input id="rq" placeholder="検索" />
    <div id="rlist">${found.items.map(routeCard).join("")}</div>
  </section>`;
  $("#rf").onsubmit = async (e) => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    const r = await api("/api/v1/custom-routes", { method: "POST", json: fd });
    if (r.similar?.length) toast("似た原典があります。参加を検討できます");
    toast(r.status === "published" ? "公開されました" : "審査中です");
    routesView();
  };
  $("#rq").oninput = debounce(async () => {
    const r = await api(`/api/v1/custom-routes/search?q=${encodeURIComponent($("#rq").value)}`);
    $("#rlist").innerHTML = r.items.map(routeCard).join("");
    bindRoutes();
  }, 200);
  bindRoutes();
}

function routeCard(r) {
  return `<article class="card">
    <p>${escapeHtml(r.trunk_text)} / ${escapeHtml(r.branch_text)}</p>
    <h2>${escapeHtml(r.leaf_text)}</h2>
    <div class="row">
      ${r.adopted ? `<button class="btn secondary" data-drop="${r.id}">採用を解除</button>` : `<button class="btn" data-adopt="${r.id}">自分の木に追加</button>`}
      ${r.can_react ? `<button class="btn secondary" data-react="custom_route:${r.id}">共感</button>` : ""}
    </div>
  </article>`;
}

function bindRoutes() {
  document.querySelectorAll("[data-adopt]").forEach((b) => b.onclick = async () => {
    const note = prompt("自分だけに見えるメモ（任意）", "") || "";
    await api(`/api/v1/custom-routes/${b.dataset.adopt}/adopt`, { method: "POST", json: { personal_note: note } });
    toast("追加しました。文言は編集できません");
    routesView();
  });
  document.querySelectorAll("[data-drop]").forEach((b) => b.onclick = async () => {
    await api(`/api/v1/custom-routes/${b.dataset.drop}/adoption`, { method: "DELETE" });
    routesView();
  });
  document.querySelectorAll("[data-react]").forEach((b) => b.onclick = async () => {
    const [type, id] = b.dataset.react.split(":");
    await api(`/api/v1/reactions/${type}/${id}`, { method: "PUT", json: {} });
    toast("共感しました");
  });
}

async function decorateView() {
  navShow(true);
  const images = await api("/api/v1/me/post-images");
  const current = await api(`/api/v1/trees/${me.id}/decorations`);
  const selected = new Map(current.items.map((x, i) => [x.id, i]));
  app.innerHTML = `<section class="panel stack">
    <h1>飾る画像（最大12）</h1>
    <p class="muted">空の枠は出しません。権限のない人には表示されません。</p>
    <form id="df" class="stack">
      ${images.items.map((im) => `<label class="row">
        <input type="checkbox" name="img" value="${im.id}" />
        <img src="${im.thumb_url}" width="72" alt="" />
        <span>${escapeHtml(im.caption)}</span>
        <select name="vis-${im.id}">
          <option value="private">自分のみ</option>
          <option value="friends">友達</option>
          <option value="same_origin_route">同じルートの人</option>
        </select>
      </label>`).join("") || "<p>投稿画像がまだありません</p>"}
      <button class="btn">保存</button>
    </form>
  </section>`;
  $("#df").onsubmit = async (e) => {
    e.preventDefault();
    const ids = [...document.querySelectorAll("[name=img]:checked")].map((x) => Number(x.value)).slice(0, 12);
    const items = ids.map((id) => ({ post_image_id: id, visibility: $(`[name=vis-${id}]`).value }));
    await api("/api/v1/me/tree-decorations", { method: "PUT", json: { items } });
    toast("飾りました");
    location.hash = "#tree";
  };
}

async function settingsView() {
  navShow(true);
  app.innerHTML = `<section class="panel stack">
    <h1>設定</h1>
    <p>成長の段階名だけが表示されます。件数は出しません。</p>
    <p>${me.growth ? escapeHtml(me.growth.name) : "未完成"}</p>
    <a class="btn secondary" href="#tree">木を再編集</a>
    <button class="btn secondary" id="export">データを出力</button>
    ${me.is_admin ? `<a class="btn secondary" href="#admin">管理</a>` : ""}
    <button class="btn danger" id="bye">退会する</button>
    <button class="btn ghost" id="out">ログアウト</button>
  </section>`;
  $("#export").onclick = async () => {
    const data = await api("/api/v1/me/export");
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "tree-of-life-export.json";
    a.click();
  };
  $("#out").onclick = async () => { await api("/api/v1/auth/logout", { method: "POST", json: {} }); location.hash = "#landing"; route(); };
  $("#bye").onclick = async () => {
    if (!confirm("退会します。よろしいですか？")) return;
    await api("/api/v1/me/delete", { method: "POST", json: {} });
    location.hash = "#landing";
    route();
  };
}

async function adminView() {
  if (!me.is_admin) { app.innerHTML = "<p>権限がありません</p>"; return; }
  const data = await api("/api/v1/admin/reports");
  const audit = await api("/api/v1/admin/audit");
  app.innerHTML = `<section class="stack"><h1>管理</h1>
    ${data.items.map((r) => `<div class="card"><p>${r.ticket} ${r.target_type} ${r.reason} ${r.status}</p>
      <button class="btn" data-hide="${r.id}">非表示</button></div>`).join("")}
    <h2>監査ログ</h2>
    ${audit.items.map((a) => `<p class="muted">${escapeHtml(a.action)} ${escapeHtml(a.target_type)}</p>`).join("")}
  </section>`;
  document.querySelectorAll("[data-hide]").forEach((b) => b.onclick = async () => {
    await api(`/api/v1/admin/reports/${b.dataset.hide}/actions`, { method: "POST", json: { action: "hide" } });
    adminView();
  });
}

function debounce(fn, ms) {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

let routeGen = 0;

async function route() {
  const gen = ++routeGen;
  await refreshMe();
  if (gen !== routeGen) return;
  const h = hash();
  if (!me && h !== "landing") {
    location.hash = "#landing";
    return landing();
  }
  const map = {
    landing: landing,
    age: ageView,
    profile: profileView,
    tree: treeView,
    timeline: timelineView,
    discover: discoverView,
    friends: friendsView,
    messages: messagesView,
    routes: routesView,
    decorate: decorateView,
    settings: settingsView,
    admin: adminView,
  };
  (map[h] || landing)();
}

window.addEventListener("hashchange", route);
route();
