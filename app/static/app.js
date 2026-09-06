const $ = (s) => document.querySelector(s);
const state = {
  me: null,
  catalog: null,
  pick: { limb: null, bough: null, grain: null },
  avatar: "/static/presets/1.svg",
  thread: null,
};

async function api(path, opts = {}) {
  const res = await fetch(path, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  if (res.status === 401) throw new Error("auth");
  const ct = res.headers.get("content-type") || "";
  if (!ct.includes("json")) return res;
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "error");
  return data;
}

function show(id) {
  for (const el of document.querySelectorAll(".panel")) el.classList.add("hidden");
  if (id) $(id).classList.remove("hidden");
}

function polar(cx, cy, r, a) {
  return [cx + r * Math.cos(a), cy + r * Math.sin(a)];
}

function drawTree() {
  const cat = state.catalog;
  if (!cat) return;
  const W = 800, H = 800, cx = 400, cy = 560;
  const limbs = cat.limbs;
  const n = limbs.length;
  let svg = `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">
    <defs>
      <radialGradient id="glow" cx="50%" cy="70%"><stop offset="0%" stop-color="#7cffb2" stop-opacity=".25"/><stop offset="100%" stop-color="#06140c" stop-opacity="0"/></radialGradient>
    </defs>
    <circle cx="${cx}" cy="${cy}" r="240" fill="url(#glow)"/>
    <ellipse class="stump" cx="${cx}" cy="${cy + 28}" rx="54" ry="22"/>
    <ellipse class="stump-ring" cx="${cx}" cy="${cy + 18}" rx="38" ry="12"/>
    <rect x="${cx - 18}" y="${cy - 40}" width="36" height="58" rx="8" fill="#4a311c"/>`;

  limbs.forEach((limb, i) => {
    const a = (-Math.PI * 1.05) + (i / (n - 1)) * Math.PI * 1.1;
    const [x2, y2] = polar(cx, cy - 36, 280, a);
    const [mx, my] = polar(cx, cy - 36, 140, a - 0.12);
    const live = state.pick.limb === limb.id;
    const dim = state.pick.limb && !live;
    const cls = `limb${live ? " live" : ""}${dim ? " dim" : ""}`;
    svg += `<g class="${cls}" data-limb="${limb.id}">
      <path class="wood" d="M ${cx} ${cy - 36} Q ${mx} ${my} ${x2} ${y2}"/>
      <text x="${x2}" y="${y2 - 10}" text-anchor="middle" fill="${live ? "#c8f542" : "#8aa892"}" font-size="11" font-family="Syne">${limb.en}</text>
    </g>`;
    if (live) {
      limb.boughs.forEach((b, j) => {
        const da = a - 0.22 + (j / 9) * 0.44;
        const [bx, by] = polar(x2, y2, 70, da);
        const on = state.pick.bough === b.id;
        svg += `<g class="bough" data-bough="${b.id}" style="cursor:pointer">
          <line x1="${x2}" y1="${y2}" x2="${bx}" y2="${by}" stroke="${on ? "#c8f542" : "#2d6a45"}" stroke-width="${on ? 4 : 2}"/>
          <circle cx="${bx}" cy="${by}" r="${on ? 6 : 4}" fill="${on ? "#c8f542" : "#7cffb2"}"/>
        </g>`;
      });
    }
  });

  if (state.pick.limb && state.pick.bough) {
    cat.grains.forEach((g, i) => {
      const x = 160 + i * 120;
      const y = 740;
      const on = state.pick.grain === g.id;
      svg += `<g class="grain-node${on ? " on" : ""}" data-grain="${g.id}">
        <circle cx="${x}" cy="${y}" r="16"/>
        <text x="${x}" y="${y + 36}" text-anchor="middle" fill="#d4af77" font-size="12">${g.ja}</text>
      </g>`;
    });
  }
  svg += `</svg>`;
  $("#tree").innerHTML = svg;
  $("#tree").querySelectorAll(".limb").forEach((el) => {
    el.onclick = () => {
      state.pick.limb = el.dataset.limb;
      state.pick.bough = null;
      state.pick.grain = null;
      drawTree();
      updateHud();
    };
  });
  $("#tree").querySelectorAll(".bough").forEach((el) => {
    el.onclick = (e) => {
      e.stopPropagation();
      state.pick.bough = el.dataset.bough;
      state.pick.grain = null;
      drawTree();
      updateHud();
    };
  });
  $("#tree").querySelectorAll(".grain-node").forEach((el) => {
    el.onclick = (e) => {
      e.stopPropagation();
      state.pick.grain = el.dataset.grain;
      drawTree();
      updateHud();
    };
  });
}

function updateHud() {
  const cat = state.catalog;
  if (!cat) return;
  const limb = cat.limbs.find((l) => l.id === state.pick.limb);
  const bough = limb?.boughs.find((b) => b.id === state.pick.bough);
  const grain = cat.grains.find((g) => g.id === state.pick.grain);
  const parts = [limb?.ja, bough?.ja, grain?.ja].filter(Boolean);
  $("#hud-path").textContent = parts.join(" · ") || "中央の木から、大枝を選ぶ";
}

function presets() {
  const box = $("#presets");
  box.innerHTML = "";
  for (let i = 1; i <= 6; i++) {
    const src = `/static/presets/${i}.svg`;
    const img = document.createElement("img");
    img.src = src;
    img.onclick = () => {
      state.avatar = src;
      box.querySelectorAll("img").forEach((x) => x.classList.remove("on"));
      img.classList.add("on");
    };
    if (i === 1) img.classList.add("on");
    box.appendChild(img);
  }
}

async function refreshMe() {
  const data = await api("/api/me");
  state.me = data.user;
  $("#btn-google").classList.toggle("hidden", !data.google);
  if (!data.user) {
    $("#landing").classList.add("on");
    $("#nav").classList.add("hidden");
    $("#home-hud").classList.add("hidden");
    $("#onboard").classList.add("hidden");
    return;
  }
  $("#landing").classList.remove("on");
  $("#nav").classList.remove("hidden");
  $("#home-hud").classList.remove("hidden");
  $("#name").value = data.user.display_name || "";
  $("#city").value = data.user.city || "";
  $("#blurb").value = data.user.blurb || "";
  if (data.user.tree) {
    state.pick = {
      limb: data.user.tree.limb_id,
      bough: data.user.tree.bough_id,
      grain: data.user.tree.grain_id,
    };
    state.avatar = data.user.avatar_url;
    $("#onboard").classList.add("hidden");
  } else {
    $("#onboard").classList.remove("hidden");
  }
  drawTree();
  updateHud();
}

async function saveTree() {
  if (!state.pick.limb || !state.pick.bough || !state.pick.grain) {
    alert("大枝・枝脈・木目を選んでください");
    return;
  }
  await api("/api/onboarding", {
    method: "POST",
    body: JSON.stringify({
      display_name: $("#name").value || "Walker",
      city: $("#city").value,
      blurb: $("#blurb").value,
      limb_id: state.pick.limb,
      bough_id: state.pick.bough,
      grain_id: state.pick.grain,
      avatar_kind: "preset",
      avatar_url: state.avatar,
    }),
  });
  await refreshMe();
  show("#discover");
  loadDiscover();
}

async function loadDiscover() {
  const { people } = await api("/api/discover");
  const box = $("#people");
  if (!people.length) {
    box.innerHTML = `<p class="lead">この枝脈には、まだ他の株がない。</p>`;
    return;
  }
  box.innerHTML = people
    .map(
      (p) => `<div class="card">
      <img src="${p.avatar_url}" alt=""/>
      <div>
        <div>${p.display_name}</div>
        <div class="meta">${p.tree?.grain || ""} · ${p.city || "somewhere"}</div>
        <div class="meta">${p.blurb || ""}</div>
        <button class="solid" data-ask="${p.id}">話してみる</button>
      </div>
    </div>`
    )
    .join("");
  box.querySelectorAll("[data-ask]").forEach((btn) => {
    btn.onclick = async () => {
      const intro = prompt("一言（任意・40字）") || "";
      await api("/api/requests", { method: "POST", body: JSON.stringify({ to_id: Number(btn.dataset.ask), intro }) });
      btn.textContent = "送った";
    };
  });
}

async function loadInbox() {
  const data = await api("/api/inbox");
  $("#reqs").innerHTML = data.requests
    .map((r) => {
      if (!r.other) return "";
      const act = !r.from_me && r.status === "pending"
        ? `<button class="solid" data-acc="${r.id}">受ける</button><button class="ghost" data-dec="${r.id}">静かに閉じる</button>`
        : `<span class="meta">${r.status}</span>`;
      return `<div class="card"><img src="${r.other.avatar_url}"/><div><div>${r.other.display_name}</div><div class="meta">${r.intro || ""}</div>${act}</div></div>`;
    })
    .join("");
  $("#threads").innerHTML = data.threads
    .map(
      (t) => `<div class="card" data-th="${t.id}" style="cursor:pointer"><img src="${t.other?.avatar_url}"/><div><div>${t.other?.display_name}</div><div class="meta">${t.last}</div></div></div>`
    )
    .join("");
  $("#reqs").querySelectorAll("[data-acc]").forEach((b) => {
    b.onclick = async () => {
      await api(`/api/requests/${b.dataset.acc}/decide`, { method: "POST", body: JSON.stringify({ accept: true }) });
      loadInbox();
    };
  });
  $("#reqs").querySelectorAll("[data-dec]").forEach((b) => {
    b.onclick = async () => {
      await api(`/api/requests/${b.dataset.dec}/decide`, { method: "POST", body: JSON.stringify({ accept: false }) });
      loadInbox();
    };
  });
  $("#threads").querySelectorAll("[data-th]").forEach((el) => {
    el.onclick = () => openThread(el.dataset.th);
  });
}

async function openThread(id) {
  state.thread = id;
  const t = await api(`/api/threads/${id}`);
  show("#chat");
  $("#chat-name").textContent = t.other.display_name;
  $("#msgs").innerHTML = t.messages.map((m) => `<div class="msg ${m.mine ? "mine" : "theirs"}">${m.body}</div>`).join("");
}

$("#btn-send").onclick = async () => {
  if (!state.thread) return;
  const body = $("#msg").value.trim();
  if (!body) return;
  await api(`/api/threads/${state.thread}/messages`, { method: "POST", body: JSON.stringify({ body }) });
  $("#msg").value = "";
  openThread(state.thread);
};

document.querySelectorAll("[data-go]").forEach((b) => {
  b.onclick = () => {
    const go = b.dataset.go;
    if (go === "home") {
      show(null);
      $("#onboard").classList.add("hidden");
    }
    if (go === "discover") {
      show("#discover");
      loadDiscover();
    }
    if (go === "inbox") {
      show("#inbox");
      loadInbox();
    }
    if (go === "edit") {
      $("#onboard").classList.remove("hidden");
      show("#onboard");
    }
  };
});

$("#btn-demo").onclick = async () => {
  await api("/api/auth/demo", { method: "POST", body: "{}" });
  await refreshMe();
};
$("#btn-google").onclick = () => {
  location.href = "/api/auth/google";
};
$("#btn-mail").onclick = () => $("#mail-panel").classList.remove("hidden");
$("#btn-mail-close").onclick = () => $("#mail-panel").classList.add("hidden");
$("#btn-send-magic").onclick = async () => {
  const email = $("#email").value.trim();
  const data = await api("/api/auth/magic", { method: "POST", body: JSON.stringify({ email }) });
  $("#magic-msg").innerHTML = data.dev_link
    ? `SMTP未設定のため、ここから入れます: <a href="${data.dev_link}">森に入る</a>`
    : data.message;
};
$("#btn-logout").onclick = async () => {
  await api("/api/auth/logout", { method: "POST", body: "{}" });
  location.reload();
};
$("#btn-save-tree").onclick = saveTree;

$("#upload").onchange = async (e) => {
  const f = e.target.files[0];
  if (!f) return;
  const fd = new FormData();
  fd.append("file", f);
  const res = await fetch("/api/avatar/upload", { method: "POST", body: fd, credentials: "include" });
  const data = await res.json();
  state.avatar = data.url;
};
$("#selfie").onchange = async (e) => {
  const f = e.target.files[0];
  if (!f) return;
  const fd = new FormData();
  fd.append("file", f);
  $("#gen-msg").textContent = "葉が色づく…";
  const res = await fetch("/api/avatar/generate", { method: "POST", body: fd, credentials: "include" });
  const data = await res.json();
  if (!res.ok) {
    $("#gen-msg").textContent = data.detail || "生成できない";
    return;
  }
  state.avatar = data.url;
  $("#gen-msg").textContent = `採用した。残り ${data.max - data.used} 回。`;
};

(async function init() {
  state.catalog = await api("/api/catalog");
  presets();
  drawTree();
  await refreshMe();
})();
