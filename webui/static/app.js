/* 爱优护全自动视频生成工厂 - 前端交互 */
"use strict";

const $ = (id) => document.getElementById(id);

// ---------- 状态 ----------
const state = {
  prodImages: [],   // [{path,url}]
  modelImages: [],
  bgmMode: "none", bgmFile: "",
  voiceOn: false, voiceId: "", voices: [],
  tasks: [],
  pollTimer: null,
};
let pendingAction = null; // clone | bgm

// ---------- 工具 ----------
function toast(msg, ms = 3500) {
  const t = $("toast");
  t.textContent = msg;
  t.style.display = "block";
  clearTimeout(t._h);
  t._h = setTimeout(() => (t.style.display = "none"), ms);
}
async function api(url, opt = {}) {
  const r = await fetch(url, opt);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || data.msg || `HTTP ${r.status}`);
  return data;
}
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// ---------- 参考图上传 ----------
let uploadCtx = null; // {grid, kind, slotEl}

function makeSlot(i, kind) {
  const el = document.createElement("div");
  el.className = "slot";
  el.innerHTML = `<div class="plus">＋</div><div class="lab">${kind === "prod" ? "上传产品图" : "上传模特图"}</div>`;
  el.addEventListener("click", () => {
    uploadCtx = { kind, slotEl: el };
    const fi = $("fileInput");
    fi.accept = kind === "prod" ? "image/*" : "image/*";
    fi.value = "";
    fi.click();
  });
  return el;
}

function buildGrids() {
  const pg = $("prodGrid"), mg = $("modelGrid");
  pg.innerHTML = ""; mg.innerHTML = "";
  for (let i = 0; i < 9; i++) pg.appendChild(makeSlot(i, "prod"));
  for (let i = 0; i < 4; i++) mg.appendChild(makeSlot(i, "model"));
}

$("fileInput").addEventListener("change", async (e) => {
  const f = e.target.files[0];
  if (!f || !uploadCtx) return;
  const slot = uploadCtx.slotEl, kind = uploadCtx.kind;
  const fd = new FormData();
  fd.append("file", f);
  fd.append("kind", kind === "prod" ? "ref_image" : "ref_image");
  try {
    const res = await api("/api/upload", { method: "POST", body: fd });
    slot.classList.add("filled");
    slot.innerHTML = `<img src="${res.url}"><span class="del">✕</span>`;
    slot.querySelector(".del").addEventListener("click", (ev) => {
      ev.stopPropagation();
      slot.classList.remove("filled");
      slot.innerHTML = `<div class="plus">＋</div><div class="lab">${kind === "prod" ? "上传产品图" : "上传模特图"}</div>`;
      if (kind === "prod") state.prodImages = state.prodImages.filter((x) => x.path !== res.server_path);
      else state.modelImages = state.modelImages.filter((x) => x.path !== res.server_path);
      updateFee();
    });
    if (kind === "prod") state.prodImages.push({ path: res.server_path, url: res.url });
    else state.modelImages.push({ path: res.server_path, url: res.url });
    toast(`已上传 ${f.name}`);
    updateFee();
  } catch (err) {
    toast("上传失败: " + err.message);
  }
});

// ---------- 分镜数量 & 费用 ----------
let numShots = 6, duration = 10;
function updateShotInfo() {
  $("shotCount").textContent = numShots;
  $("shotInfo").textContent = `${numShots} 分镜 × ${duration}秒 = ${numShots * duration} 秒成片`;
  $("scriptText").placeholder = `【分镜1】画面描述…\n…\n【分镜${numShots}】画面描述…（或点击 ✨AI 生成分镜）`;
  updateFee();
}
function updateFee() {
  const orient = $("segOrient").querySelector(".on").dataset.v;
  const res = $("segRes").querySelector(".on").dataset.r;
  const price = { "480p": 0.04, "768p": 0.06, "1080p": 0.1 }[res];
  const perShot = Math.round(numShots * duration * price * 100) / 100;
  const aiCount = +$("aiCountSlider").value;
  $("feeEst").innerHTML = `💰 预估费用：${numShots}分镜 × ${duration}s × ${res}${orient} = <b>¥${perShot.toFixed(2)} / 条</b>；全智能 ${aiCount} 条 = ¥${(perShot * aiCount).toFixed(2)}（单条约 ${Math.ceil(numShots * 12)} 分钟）`;
}
$("btnShotMinus").onclick = () => { numShots = Math.max(1, numShots - 1); updateShotInfo(); };
$("btnShotPlus").onclick = () => { numShots = Math.min(10, numShots + 1); updateShotInfo(); };
$("aiCountSlider").addEventListener("input", (e) => {
  $("aiCountVal").textContent = e.target.value + " 条";
  updateFee();
});
$("durSlider").addEventListener("input", (e) => {
  duration = +e.target.value;
  $("durVal").textContent = duration + " 秒";
  updateShotInfo();
});
$("segOrient").addEventListener("click", (e) => {
  if (e.target.dataset.v) {
    $("segOrient").querySelectorAll("button").forEach((b) => b.classList.remove("on"));
    e.target.classList.add("on");
    updateFee();
  }
});
$("segRes").addEventListener("click", (e) => {
  if (e.target.dataset.r) {
    $("segRes").querySelectorAll("button").forEach((b) => b.classList.remove("on"));
    e.target.classList.add("on");
    updateFee();
  }
});
$("concVal") && ($("btnConcMinus").onclick = () => {
  const v = Math.max(1, +$("concVal").textContent - 1); $("concVal").textContent = v;
});
$("btnConcPlus").onclick = () => {
  const v = Math.min(10, +$("concVal").textContent + 1); $("concVal").textContent = v;
};
$("scriptText").addEventListener("input", (e) => {
  $("charCount").textContent = e.target.value.length + " 字";
});

// ---------- AI 分镜 ----------
function collectProductInfo() {
  const name = $("prodName").value.trim();
  const params = $("prodParams").value.trim();
  const sell = $("prodSell").value.trim();
  const parts = [];
  if (name) parts.push("产品名称：" + name);
  if (params) parts.push("产品参数：" + params);
  if (sell) parts.push("核心卖点：" + sell);
  return parts.join("\n");
}
function cleanDub(s) {
  if (!s) return "";
  // 剔除"画面描述:"等前缀标记，只留旁白
  s = s.replace(/^(画面描述|画面|分镜描述)\s*[：:]\s*/g, "").trim();
  if (/【分镜/.test(s)) return "";                 // 混入分镜标记 → 判脏
  const shotWords = (s.match(/镜头|画面|特写|机位|拉近|推近|切换|动作/g) || []).length;
  if (shotWords >= 2) return "";                    // 画面描述词汇过多 → 判脏
  return s;
}
$("btnAiStory").addEventListener("click", async () => {
  const btn = $("btnAiStory");
  btn.disabled = true; btn.textContent = "⏳ AI 生成中…";
  try {
    const res = await api("/api/storyboard", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        num_shots: numShots, angle: "",
        product_info: collectProductInfo(),
        template: $("selTemplate").value,
      }),
    });
    $("scriptText").value = res.shots.map((s, i) => `【分镜${i + 1}】${s}`).join("\n");
    $("charCount").textContent = $("scriptText").value.length + " 字";
    const dub = cleanDub(res.dub);
    if (dub && !$("dubText").value.trim()) {
      $("dubText").value = dub;
      toast("分镜脚本与配音旁白已生成");
    } else if (!dub && !$("dubText").value.trim()) {
      toast("⚠ AI 未生成纯口播文案，请手动填写配音文案（只写旁白台词，勿写画面描述）");
    } else {
      toast("分镜脚本已生成，可手动修改");
    }
  } catch (err) {
    toast("AI 生成失败: " + err.message);
  } finally {
    btn.disabled = false; btn.textContent = "✨ AI 生成分镜";
  }
});
$("btnClearScript").onclick = () => { $("scriptText").value = ""; $("charCount").textContent = "0 字"; };

// ---------- 配音 ----------
$("voiceSwitch").addEventListener("click", () => {
  state.voiceOn = !state.voiceOn;
  $("voiceSwitch").classList.toggle("off", !state.voiceOn);
  $("voicePanel").style.display = state.voiceOn ? "block" : "none";
  if (state.voiceOn && state.voices.length === 0) loadVoices();
});
$("speedSlider").addEventListener("input", (e) => { $("speedVal").textContent = (+e.target.value).toFixed(2) + "×"; });
$("voiceVolSlider").addEventListener("input", (e) => { $("voiceVolVal").textContent = e.target.value + "%"; });

async function loadVoices() {
  try {
    state.voices = await api("/api/voices");
    const sel = $("voiceSelect");
    sel.innerHTML = "";
    state.voices.forEach((v) => {
      const o = document.createElement("option");
      o.value = v.id; o.textContent = v.name;
      sel.appendChild(o);
    });
    if (state.voices.length) {
      sel.value = state.voices[0].id;
      state.voiceId = state.voices[0].id;
      $("voicePickName").textContent = state.voices[0].name;
      $("voicePickDesc").textContent = state.voices[0].desc || "";
    } else {
      $("voicePickName").textContent = "暂无音色";
      $("voicePickDesc").textContent = "请检查网络后刷新";
    }
  } catch (err) { toast("加载音色失败: " + err.message); }
}
$("voiceSelect").addEventListener("change", (e) => {
  const v = state.voices.find((x) => x.id === e.target.value);
  if (v) {
    state.voiceId = v.id;
    $("voicePickName").textContent = v.name;
    $("voicePickDesc").textContent = v.desc || "";
  }
});
// 复用 fileInput：BGM 上传
$("fileInput").addEventListener("change", async (e) => {
  const f = e.target.files[0];
  if (!f || uploadCtx || !pendingAction) return;
  const action = pendingAction; pendingAction = null;
  if (action === "bgm") {
    const fd = new FormData();
    fd.append("file", f);
    fd.append("kind", "bgm");
    try {
      const res = await api("/api/upload", { method: "POST", body: fd });
      state.bgmFile = res.server_path;
      $("bgmFileName").textContent = f.name;
      toast("BGM 已上传");
    } catch (err) { toast("BGM 上传失败: " + err.message); }
  }
});
$("btnTtsTest").addEventListener("click", async () => {
  const text = ($("dubText").value || "").trim().slice(0, 10);
  if (!text) { toast("请先填写配音文案"); return; }
  if (!state.voiceId) { toast("请先选择音色"); return; }
  const btn = $("btnTtsTest");
  btn.disabled = true; btn.textContent = "⏳ 生成试听…";
  try {
    const res = await api("/api/tts/test", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, voice_id: state.voiceId, speed: +$("speedSlider").value }),
    });
    $("ttsWave").style.display = "flex";
    $("ttsAudio").src = res.url;
    $("ttsAudio").play().catch(() => {});
    toast("试听已生成，点击播放");
  } catch (err) {
    toast("试听失败: " + err.message);
  } finally {
    btn.disabled = false; btn.textContent = "🔊 试听配音";
  }
});

// ---------- BGM ----------
$("bgmModeSeg").addEventListener("click", (e) => {
  const m = e.target.dataset.mode;
  if (!m) return;
  state.bgmMode = m;
  $("bgmModeSeg").querySelectorAll("button").forEach((b) => b.classList.remove("on"));
  e.target.classList.add("on");
  $("bgmUploadRow").style.display = m === "upload" ? "flex" : "none";
  $("bgmLibraryRow").style.display = m === "library" ? "flex" : "none";
  if (m === "library" && !$("bgmSelect").options.length) loadBgm();
});
$("bgmVolSlider").addEventListener("input", (e) => { $("bgmVolVal").textContent = e.target.value + "%"; });
async function loadBgm() {
  try {
    const items = await api("/api/bgm");
    const sel = $("bgmSelect");
    sel.innerHTML = "";
    items.forEach((it) => {
      const o = document.createElement("option");
      o.value = it.path; o.textContent = `${it.name} (${it.size_mb}MB)`;
      sel.appendChild(o);
    });
    if (items.length) {
      state.bgmFile = items[0].path;
      $("bgmLibHint").textContent = `共 ${items.length} 首曲目`;
    } else {
      $("bgmLibHint").textContent = "曲库为空，可切换「上传」";
    }
  } catch (err) { toast("加载曲库失败: " + err.message); }
}
$("bgmSelect").addEventListener("change", (e) => { state.bgmFile = e.target.value; });
$("btnBgmUpload").addEventListener("click", () => {
  uploadCtx = null; pendingAction = "bgm";
  const fi = $("fileInput");
  fi.accept = "audio/*"; fi.value = ""; fi.click();
});

// ---------- 输出目录选择 ----------
let curDirPath = "", parentPath = "";
async function browseDir(path) {
  try {
    const res = await api("/api/dirs?path=" + encodeURIComponent(path));
    curDirPath = res.path;
    parentPath = res.parent || "";
    $("dirPath").textContent = res.path ? "📂 " + res.path : "选择盘符";
    $("btnDirParent").style.display = res.parent ? "" : "none";
    const list = $("dirList");
    list.innerHTML = "";
    res.dirs.forEach((d) => {
      const row = document.createElement("div");
      row.style.cssText = "padding:8px 10px;border-radius:8px;cursor:pointer;font-size:13px";
      row.innerHTML = `<span>📂 ${esc(d.name)}</span>`;
      row.onmouseenter = () => (row.style.background = "#f1f5f9");
      row.onmouseleave = () => (row.style.background = "");
      row.onclick = () => browseDir(d.path);
      list.appendChild(row);
    });
    if (!res.dirs.length) list.innerHTML = '<div style="color:#94a3b8;padding:14px;text-align:center;font-size:13px">空目录</div>';
  } catch (err) { toast("浏览失败: " + err.message); }
}
$("btnBrowseDir").onclick = () => { $("maskDir").classList.add("show"); browseDir(""); };
$("btnDirParent").onclick = () => parentPath && browseDir(parentPath);
$("btnDirPick").onclick = () => {
  if (!curDirPath) { toast("请先进入一个目录"); return; }
  $("outDirInput").value = curDirPath;
  $("maskDir").classList.remove("show");
  toast("输出目录已设置: " + curDirPath);
};
$("btnDirClose").onclick = () => $("maskDir").classList.remove("show");

// ---------- 开始生成 ----------
$("btnGo").addEventListener("click", async () => {
  const images = [...state.prodImages.map((x) => x.path), ...state.modelImages.map((x) => x.path)];
  if (!images.length && $("selWorkflow").value !== "text2video") {
    toast("请至少上传 1 张产品参考图"); return;
  }
  const body = {
    type: +$("aiCountSlider").value > 1 ? "ai" : "manual",
    ai_count: +$("aiCountSlider").value,
    name: $("nameInput").value.trim() || "轻便侠218_成片",
    script_text: $("scriptText").value,
    num_shots: numShots,
    duration: duration,
    resolution: $("segRes").querySelector(".on").dataset.r + $("segOrient").querySelector(".on").dataset.v,
    workflow: $("selWorkflow").value,
    images,
    concurrency: +$("concVal").textContent,
    voice_on: state.voiceOn,
    voice_id: state.voiceId,
    dub_text: $("dubText").value,
    speed: +$("speedSlider").value,
    voice_volume: +$("voiceVolSlider").value / 100,
    bgm_mode: state.bgmMode,
    bgm_file: state.bgmMode === "none" ? "" : state.bgmFile,
    bgm_name: state.bgmMode === "library" ? ($("bgmSelect").selectedOptions[0]?.textContent || "") : "",
    bgm_volume: +$("bgmVolSlider").value / 100,
    product_info: collectProductInfo(),
    template: $("selTemplate").value,
    output_dir: $("outDirInput").value.trim(),
  };
  const btn = $("btnGo");
  btn.disabled = true; btn.textContent = "⏳ 提交中…";
  try {
    const res = await api("/api/generate", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    toast(`已提交 ${res.count} 条成片任务，排队生成中`);
    refreshTasks();
  } catch (err) {
    toast("提交失败: " + err.message);
  } finally {
    btn.disabled = false; btn.textContent = "🚀 开始生成";
  }
});

// ---------- 任务渲染 ----------
function taskSig(t) {
  return [t.status, t.progress, t.stage, t.error, t.size_mb].join("|");
}
function taskCard(t) {
  const st = {
    queued: ["st-wait", "⏳ 排队中"],
    running: ["st-run", "⏳ " + t.stage],
    success: ["st-ok", "✅ 已完成"],
    failed: ["st-fail", "❌ 失败"],
  }[t.status] || ["st-wait", t.status];
  const thumb = t.status === "success" && t.out_file
    ? `<video src="/api/tasks/${t.id}/video" muted preload="metadata"></video>`
    : "🎬";
  const metaBits = [t.created_at];
  if (t.resolution) metaBits.push(t.resolution);
  if (t.duration_s) metaBits.push(`${t.duration_s}s`);
  if (t.angle) metaBits.push("AI·" + t.angle);
  if (t.voice_on) metaBits.push("🎙配音");
  if (t.bgm) metaBits.push("🎵" + t.bgm);
  if (t.status === "success") metaBits.push(`${t.size_mb}MB`);
  if (t.status === "failed") metaBits.push(t.error);
  const bar = t.status === "running" || t.status === "queued"
    ? `<div class="bar"><i style="width:${t.progress}%"></i></div>` : "";
  const actions = t.status === "success"
    ? `<a class="btn" style="padding:5px 12px;font-size:12px;text-decoration:none" href="/api/tasks/${t.id}/video" download title="下载成片">⬇</a>` : "";
  return `<div class="task" data-tid="${t.id}" data-sig="${taskSig(t)}">
    <div class="thumb" onclick="${t.status === "success" ? `this.querySelector('video').play()\`` : ""}">${thumb}</div>
    <div class="info">
      <div class="name">${esc(t.name)} <span class="tag tag-blue">${esc(metaBits.join(" · "))}</span></div>
      ${bar}
    </div>
    <span class="status ${st[0]}">${st[1]}</span>
    ${actions}
    <button class="btn" style="padding:5px 12px;font-size:12px" onclick="delTask('${t.id}')" title="删除任务记录">🗑</button>
  </div>`;
}

async function delTask(id) {
  if (!confirm("删除该任务记录？（成片文件保留）")) return;
  try {
    const res = await api("/api/tasks/" + id, { method: "DELETE" });
    if (res.ok) { toast("任务已删除"); refreshTasks(); }
    else toast(res.error || "删除失败");
  } catch (err) { toast("删除失败: " + err.message); }
}

async function refreshTasks() {
  try {
    const res = await api("/api/tasks");
    state.tasks = res.tasks || [];
    rebuildLogFilter();
    const list = $("taskList");
    if (!state.tasks.length) {
      list.innerHTML = '<div style="color:#94a3b8;font-size:13px;text-align:center;padding:20px">暂无任务</div>';
      return;
    }
    // diff 渲染：只更新状态变化的卡片，播放中的成片不被轮询打断
    const byId = new Map(state.tasks.map((t) => [t.id, t]));
    [...list.children].forEach((el) => { if (!byId.has(el.dataset.tid)) el.remove(); });
    state.tasks.forEach((t) => {
      const el = list.querySelector(`[data-tid="${t.id}"]`);
      const html = taskCard(t);
      if (!el) list.insertAdjacentHTML("beforeend", html);
      else if (el.dataset.sig !== taskSig(t)) el.outerHTML = html;
    });
  } catch (err) { /* 轮询失败忽略 */ }
}
state.pollTimer = setInterval(refreshTasks, 5000);

// ---------- 操作日志 ----------
let lastLogKey = null, logFilterTask = "";
function rebuildLogFilter() {
  const sel = $("logFilter");
  const names = [...new Set(state.tasks.map((t) => t.name))];
  const cur = sel.value;
  sel.innerHTML = '<option value="">全部任务</option>'
    + names.map((n) => `<option value="${esc(n)}">${esc(n)}</option>`).join("");
  if (names.includes(cur)) sel.value = cur;
}
async function refreshLogs(force = false) {
  try {
    const res = await api("/api/logs?limit=150");
    let logs = res.logs || [];
    if (logFilterTask) logs = logs.filter((l) => l.task === logFilterTask);
    const list = $("logList");
    if (!logs.length) {
      list.innerHTML = '<div style="color:#64748b">暂无日志…</div>';
      return;
    }
    // 有新日志才重绘
    const key = logs[0]?.time + logs[0]?.msg + logs[0]?.dur;
    if (!force && key === lastLogKey && list.childElementCount === logs.length) return;
    lastLogKey = key;
    list.innerHTML = logs.map((l) => {
      const color = l.msg.startsWith("❌") ? "#f87171"
        : l.msg.startsWith("✅") || l.msg.startsWith("🎉") ? "#4ade80"
        : /^[▶⏫⏳🎙🔗🎚⬇🚀→]/.test(l.msg) ? "#93c5fd" : "#e2e8f0";
      const dur = l.dur ? ` <span style="color:#64748b">(+${l.dur}s)</span>` : "";
      return `<div style="color:${color}"><span style="color:#64748b">[${esc(l.time)}]</span> <span style="color:#94a3b8">${esc(l.task)}</span>${dur} ${esc(l.msg)}</div>`;
    }).join("");
    list.scrollTop = list.scrollHeight;
  } catch (err) { /* 忽略轮询失败 */ }
}
setInterval(() => refreshLogs(), 4000);
$("logFilter").addEventListener("change", (e) => { logFilterTask = e.target.value; refreshLogs(true); });
$("btnSettings").onclick = async () => {
  $("mask").classList.add("show");
  try {
    const s = await api("/api/settings");
    $("inpAutodl").placeholder = s.autodl_key_set ? `已设置（${s.autodl_key}）` : "未设置，请输入 autodl.art 令牌";
    $("inpDeepseek").placeholder = s.deepseek_key_set ? `已设置（${s.deepseek_key}）` : "未设置（AI 分镜不可用）";
    refreshTtsStatus();
  } catch (err) { toast("读取设置失败: " + err.message); }
};
$("btnCloseSettings").onclick = () => $("mask").classList.remove("show");
$("btnSaveSettings").onclick = async () => {
  const body = {};
  if ($("inpAutodl").value.trim()) body.autodl_key = $("inpAutodl").value.trim();
  if ($("inpDeepseek").value.trim()) body.deepseek_key = $("inpDeepseek").value.trim();
  try {
    await api("/api/settings", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    toast("设置已保存");
    $("inpAutodl").value = ""; $("inpDeepseek").value = "";
  } catch (err) { toast("保存失败: " + err.message); }
};
async function refreshTtsStatus() {
  try {
    const s = await api("/api/tts/status");
    $("svcStatus").innerHTML = s.running
      ? `服务状态：<b style="color:#10b981">● ${s.provider || "edge-tts"} 就绪</b>（免费在线，无需本地服务）`
      : `服务状态：<b style="color:#dc2626">● 不可用</b>`;
  } catch { $("svcStatus").textContent = "服务状态：无法检测"; }
}

// ---------- 初始化 ----------
buildGrids();
updateShotInfo();
loadBgm();
loadVoices();
refreshTasks();
