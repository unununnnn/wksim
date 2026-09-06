"use strict";
(() => {
  const $ = id => document.getElementById(id);
  const pretty = value => value == null ? "暂无反馈" : JSON.stringify(value, null, 2);
  const copy = value => JSON.parse(JSON.stringify(value));
  const terminal = run => run && ["pass", "failed", "cancelled"].includes(run.status);
  const active = run => run && ["queued", "running"].includes(run.status);
  const labels = { queued: "排队中", running: "运行中", pass: "通过", failed: "失败", cancelled: "已取消", unowned: "历史记录 · 无当前归属" };
  const state = { csrf: null, defaults: {}, configs: [], config: null, jsonValid: true, savedName: null, revision: null, runs: [], selected: null, ticket: null, edit: 0, busy: false, online: false, ue: false, offset: 0, total: 0, evidenceLoaded: false, stopped: false, booting: false, cancelTarget: null };
  const canonical = value => JSON.stringify(value, (_, v) => v && typeof v === "object" && !Array.isArray(v) ? Object.keys(v).sort().reduce((o, k) => { o[k] = v[k]; return o; }, {}) : v);
  const actionFields = ["mission_id", "control_epoch", "native_generation", "action_token"];
  const actionRecords = new Map(), detailTimes = new WeakMap();
  let actionDialog = null, actionBusy = false;
  const actionName = value => value === "pause" ? "暂停" : "显式恢复";
  const actionKey = target => canonical([target.id, target.run_id, ...actionFields.map(k => target[k])]);
  function freshActionRun(run) {
    const age = performance.now() - (detailTimes.get(run) ?? -Infinity);
    return state.online && !state.booting && navigator.onLine !== false && run?.kind === "flight" && run.status === "running" &&
      run.live?.freshness?.status === "live" && age >= 0 && age < 2500;
  }
  function offeredAction(run, action) {
    const offer = run?.live?.action_offer;
    return freshActionRun(run) && typeof run.run_id === "string" && Boolean(run.run_id) && offer?.version === 1 &&
      ["mission_id", "control_epoch", "action_token"].every(k => typeof offer[k] === "string" && offer[k].length > 0) &&
      Number.isSafeInteger(offer.native_generation) && offer.native_generation >= 0 &&
      Array.isArray(offer.allowed_actions) && offer.allowed_actions.length === 1 && offer.allowed_actions[0] === action;
  }
  function frozenAction(run, action) {
    return Object.freeze({ id: run.id, run_id: run.run_id, kind: run.kind, version: 1, action,
      ...Object.fromEntries(actionFields.map(k => [k, run.live.action_offer[k]])) });
  }
  function sameActionRun(target, run) {
    return run?.id === target.id && run.run_id === target.run_id && run.kind === target.kind &&
      actionFields.every(k => run.live?.action_offer?.[k] === target[k]);
  }
  function validActionDialog(target) {
    return actionDialog === target && !target.invalid && sameActionRun(target.frozen, state.selected) &&
      offeredAction(state.selected, target.frozen.action);
  }
  function invalidateActionDialog(message) {
    if (!actionDialog) return;
    actionDialog.invalid = true;
    $("mission-action-dialog-note").textContent = message;
    $("mission-action-confirm").disabled = true;
    if (document.activeElement === $("mission-action-confirm")) $("mission-action-back").focus();
  }
  function matchingRequest(target, request) {
    return request?.version === 1 && request.run_id === target.run_id && request.action === target.action &&
      typeof request.request_id === "string" && request.request_id.length > 0 && actionFields.every(k => request[k] === target[k]);
  }
  function observeActionFeedback(run) {
    const progress = [...(Array.isArray(run.live?.events) ? run.live.events.filter(e => e.stream === "mission").map(e => e.payload) : []), run.live?.mission];
    for (const record of actionRecords.values()) {
      if (record.target.id !== run.id || record.target.run_id !== run.run_id) continue;
      for (const p of progress) {
        const event = p?.event;
        const expected = record.target.action === "pause" ? ["mission_pausing", "mission_paused"] : ["mission_resume_received", "mission_resumed"];
        if (!expected.includes(event) || p.mission_id !== record.target.mission_id || p.run_id !== record.target.run_id ||
          p.control_epoch !== record.target.control_epoch || p.native_generation !== record.target.native_generation) continue;
        const request = event === "mission_paused" ? p.pause?.pause_request : event === "mission_resumed" ? p.pause?.resume_request : p.action_request;
        if (!matchingRequest(record.target, request) || (record.request && request.request_id !== record.request.request_id)) continue;
        // Without the response request_id, correlated evidence cannot confirm this request.
        if (!record.request) { record.related = request.request_id; continue; }
        record.feedback = record.feedback === expected[1] ? record.feedback : event;
      }
      if (!sameActionRun(record.target, run) || run.status !== "running") record.invalid = true;
    }
  }
  function renderMissionActions() {
    const run = state.selected;
    if (actionDialog && !actionDialog.invalid && !validActionDialog(actionDialog)) invalidateActionDialog("确认已失效：选择、连接、数据新鲜度或任务身份已变化。请返回观察后重新选择动作。");
    for (const action of ["pause", "resume"]) {
      const allowed = offeredAction(run, action), used = allowed && actionRecords.has(actionKey(frozenAction(run, action)));
      $("mission-" + action).disabled = state.busy || actionBusy || Boolean(actionDialog) || !allowed || used;
      $("mission-" + action).setAttribute("aria-busy", String(actionBusy && actionDialog?.frozen.action === action));
    }
    $("mission-action-confirm").disabled = actionBusy || state.busy || !actionDialog || !validActionDialog(actionDialog);
    $("mission-action-confirm").setAttribute("aria-busy", String(actionBusy));
    $("mission-action-confirm").textContent = actionBusy ? "正在核对 / 提交…" : `确认${actionName(actionDialog?.frozen.action)}`;
    $("mission-action-availability").textContent = !freshActionRun(run) ? "暂停 / 恢复不可用：需要在线、运行中的飞行实验及最新实时反馈。" :
      `服务动作许可：${run.live?.action_offer?.allowed_actions?.map(actionName).join("、") || "暂无"} · 原因：${run.live?.action_offer?.reason || "未返回"}`;
    const notes = [...actionRecords.values()].filter(r => r.target.id === run?.id).map(r => {
      const done = ["mission_paused", "mission_resumed"].includes(r.feedback);
      const status = r.rejected ? `服务已拒绝请求：${r.rejected}；禁止自动重试` : done ? "已匹配该请求的任务确认反馈（不代表物理停止或落地）" : r.feedback ? "已匹配该请求的任务受理反馈，等待动作确认" : r.unknown ? "结果未知，禁止自动重试" : "文件已提交，等待匹配的任务反馈；尚未确认飞控完成";
      return `${actionName(r.target.action)}：${status}${r.invalid ? "；原令牌已失效" : ""}\nrequest_id: ${r.request?.request_id || "响应未取得"}${r.related ? `；同令牌反馈 request_id: ${r.related}（缺少响应身份，未确认本请求）` : ""}`;
    });
    $("mission-action-note").textContent = notes.join("\n\n") || "尚未提交暂停 / 恢复操作。提交后不会自动重试。";
  }
  function openMissionAction(action) {
    const run = state.selected;
    if (state.busy || actionBusy || actionDialog || !offeredAction(run, action)) return;
    const frozen = frozenAction(run, action);
    if (actionRecords.has(actionKey(frozen))) return;
    actionDialog = { frozen, invalid: false };
    $("mission-action-title").textContent = `${actionName(action)}当前任务？`;
    $("mission-action-target").textContent = pretty(frozen);
    $("mission-action-description").textContent = action === "pause" ?
      "暂停停止任务派点，物理仿真与飞控继续运行；PX4 请求 AUTO.LOITER，ArduPilot 请求 BRAKE。请等待任务反馈。" :
      "恢复是新的显式接管。BODY 航点保持原记录的 ENU 目标并重新完整驻留。若取消已提交，恢复意味着接管后 LAND，不再执行航点；取消本身不会自动抢回控制。";
    $("mission-action-dialog-note").textContent = "确认前会重新读取并核对冻结身份；不会自动替换为新令牌。";
    renderMissionActions(); $("mission-action-dialog").showModal(); $("mission-action-back").focus();
  }
  async function submitMissionAction() {
    const dialog = actionDialog;
    if (state.busy || actionBusy || !dialog || !validActionDialog(dialog)) { renderMissionActions(); return; }
    actionBusy = true; state.busy = true; controls();
    let record;
    try {
      const target = dialog.frozen, latest = await api(`/api/runs/${encodeURIComponent(target.id)}`);
      if (!validActionDialog(dialog) || !sameActionRun(target, latest) || !offeredAction(latest, target.action)) throw new Error("任务身份、动作许可或连接已变化，未提交。请重新确认。");
      state.selected = latest; upsert(latest);
      if (actionRecords.has(actionKey(target))) throw new Error("该令牌已有操作记录，禁止重复提交。");
      record = { target, unknown: true, request: null };
      actionRecords.set(actionKey(target), record);
      const response = await api(`/api/runs/${encodeURIComponent(target.id)}/mission-action`, {
        mission_id: target.mission_id, action_token: target.action_token, action: target.action,
        control_epoch: target.control_epoch, native_generation: target.native_generation
      });
      if (response.submitted !== true || !matchingRequest(target, response.request)) throw new Error("提交响应缺少匹配身份，结果未知。");
      record.request = Object.freeze(copy(response.request)); record.unknown = false;
      if (state.selected) observeActionFeedback(state.selected);
      $("mission-action-dialog").close();
    } catch (e) {
      if (record && [400, 403, 404].includes(e.httpStatus)) { record.rejected = e.message; record.unknown = false; }
      invalidateActionDialog(record ? `${record.rejected ? "服务已拒绝请求" : "结果未知"}：${e.message}。已保留该令牌记录，禁止自动重试。` : e.message);
    } finally { actionBusy = false; state.busy = false; controls(); }
  }
  async function hash(config) {
    const bytes = new TextEncoder().encode(canonical(config));
    return Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)), b => b.toString(16).padStart(2, "0")).join("");
  }
  async function api(path, body) {
    const response = await fetch(path, { method: body === undefined ? "GET" : "POST", credentials: "same-origin", cache: "no-store", headers: body === undefined ? {} : { "Content-Type": "application/json", "X-Wksim-CSRF": state.csrf || "" }, body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(15000) });
    const data = await response.json();
    if (!response.ok) { const error = new Error(data.error || `HTTP ${response.status}`); error.httpStatus = response.status; throw error; }
    if (body === undefined && /^\/api\/runs\/[^/?]+$/.test(path)) { detailTimes.set(data, performance.now()); observeActionFeedback(data); }
    return data;
  }
  function clearErrors() {
    $("errors").hidden = true; $("error-list").replaceChildren();
    document.querySelectorAll('[aria-invalid="true"]').forEach(el => el.removeAttribute("aria-invalid"));
    ["name-error", "json-error", "points-error", "evidence-error", "action-error"].forEach(id => { $(id).textContent = ""; });
  }
  function error(message, target = "config-json", inline = "json-error") {
    $(inline === "run-error" ? "action-error" : inline).textContent = message;
    const field = $(target); field.setAttribute("aria-invalid", "true");
    const item = document.createElement("li"), link = document.createElement("a");
    link.href = `#${target}`; link.textContent = message;
    link.addEventListener("click", event => { event.preventDefault(); if (target === "config-json") $("advanced").open = true; field.focus(); });
    item.append(link); $("error-list").append(item); $("errors").hidden = false; $("errors").focus();
  }
  function invalidate() { state.edit++; state.ticket = null; $("preflight-note").textContent = "配置已变更，原预检票据失效。请重新预检；候选准入不等于定位或飞行就绪。"; controls(); }
  function currentConfig() {
    const config = JSON.parse($("config-json").value);
    if (!config || typeof config !== "object" || Array.isArray(config)) throw new Error("完整配置必须为 JSON 对象。");
    return config;
  }
  function syncJSON() { $("config-json").value = pretty(state.config); }
  function renderPoints() {
    const points = state.config?.mission?.waypoints;
    $("waypoints").replaceChildren();
    if (!Array.isArray(points)) { $("points-error").textContent = "配置没有有效的 mission.waypoints；请在高级 JSON 中修正。"; controls(); return; }
    points.forEach((point, index) => {
      const card = document.createElement("div"); card.className = "waypoint";
      const heading = document.createElement("div"); heading.className = "waypoint-heading";
      const title = document.createElement("h3"); title.textContent = `任务点 ${String(index + 1).padStart(2, "0")}`;
      const remove = document.createElement("button"); remove.type = "button"; remove.textContent = "移除"; remove.disabled = points.length <= 1; remove.setAttribute("aria-label", `移除任务点 ${index + 1}`);
      remove.onclick = () => { points.splice(index, 1); invalidate(); syncJSON(); renderPoints(); $("add-point").focus(); };
      heading.append(title, remove); card.append(heading);
      const fields = document.createElement("div"); fields.className = "point-fields";
      ["frame", "x", "y", "z", "yaw", "dwell"].forEach(key => {
        const wrapper = document.createElement("div"), label = document.createElement("label"), input = document.createElement("input");
        const id = `point-${index}-${key}`; input.id = id; label.htmlFor = id; label.textContent = { frame: "frame 坐标系", x: "x / m", y: "y / m", z: "z / m", yaw: "yaw / rad", dwell: "dwell / s" }[key];
        input.type = key === "frame" ? "text" : "number"; if (key !== "frame") input.step = "any";
        input.value = key === "frame" ? point?.frame ?? "" : key === "yaw" ? point?.yaw_rad ?? "" : key === "dwell" ? point?.dwell_s ?? "" : point?.position_m?.[["x", "y", "z"].indexOf(key)] ?? "";
        input.addEventListener("input", () => {
          if (!points[index] || typeof points[index] !== "object") points[index] = {};
          const p = points[index], v = key === "frame" ? input.value : input.value === "" ? null : Number(input.value);
          if (key === "frame") p.frame = v; else if (key === "yaw") p.yaw_rad = v; else if (key === "dwell") p.dwell_s = v; else { if (!Array.isArray(p.position_m)) p.position_m = [null, null, null]; p.position_m[["x", "y", "z"].indexOf(key)] = v; }
          invalidate(); syncJSON();
        });
        wrapper.append(label, input); fields.append(wrapper);
      });
      card.append(fields); $("waypoints").append(card);
    });
    controls();
  }
  function setConfig(config, name = "", revision = null) {
    state.config = copy(config); state.jsonValid = true; state.savedName = revision == null ? null : name; state.revision = revision;
    $("name").value = name; $("stack").value = config.stack || ""; $("revision").textContent = revision == null ? "未保存" : `版本 ${revision}`;
    invalidate(); syncJSON(); renderPoints();
  }
  function controls() {
    renderMissionActions();
    const ready = state.online && !state.busy && Boolean(state.config), run = state.selected;
    $("editor").disabled = !state.online || state.busy || !state.config;
    $("preflight").disabled = !ready;
    $("start").disabled = !ready || !state.ticket || state.ticket.status !== "pass" || state.ticket.edit !== state.edit || state.runs.some(r => r.kind === "flight" && active(r));
    $("with-view").disabled = !ready || !state.ue;
    $("add-point").disabled = !state.jsonValid || !Array.isArray(state.config?.mission?.waypoints) || state.config.mission.waypoints.length >= 8;
    $("cancel").disabled = !state.online || state.busy || run?.kind !== "flight" || !active(run) || !missionId(run);
    $("view-open").disabled = !state.online || state.busy || !state.ue || run?.kind !== "flight" || !active(run);
    $("view-close").disabled = !state.online || state.busy || !run || !run.view || ["stopped", "unavailable"].includes(run.view.state);
    $("load-result").disabled = !state.online || state.busy || !terminal(run);
    $("load-evidence").disabled = !state.online || state.busy || run?.kind !== "flight" || !terminal(run);
    $("prev").disabled = !state.online || state.busy || !state.evidenceLoaded || state.offset === 0;
    $("next").disabled = !state.online || state.busy || !state.evidenceLoaded || state.offset + 50 >= state.total;
    $("shutdown").disabled = !state.online || state.busy;
  }
  function missionId(run) { return run?.live?.mission?.mission_id ?? run?.result?.task?.mission?.mission_id ?? null; }
  function upsert(run) { const index = state.runs.findIndex(r => r.id === run.id); if (index < 0) state.runs.unshift(run); else state.runs[index] = run; }
  function resetEvidence() { state.offset = 0; state.total = 0; state.evidenceLoaded = false; $("records").textContent = "记录：尚未读取"; $("diagnostics").textContent = "诊断：尚未读取"; $("result").textContent = "尚未读取结果"; $("page").textContent = "尚未读取"; }
  function selectRun(run) { invalidateActionDialog("选择已变化，原确认失效，请返回后重新选择动作。"); state.selected = run; resetEvidence(); $("cancel-note").textContent = "取消不会自动抢回控制。暂停时取消已提交，需显式恢复接管后 LAND；请求受理不等于落地。"; renderRun(); renderRuns(); }
  function renderRuns() {
    if (document.activeElement?.closest("#runs")) return;
    $("runs").replaceChildren();
    if (!state.runs.length) { $("runs").textContent = "尚无本控制台创建的实验。"; return; }
    state.runs.forEach(run => {
      const button = document.createElement("button"); button.className = "run-item"; button.setAttribute("aria-pressed", String(run.id === state.selected?.id));
      button.textContent = `${run.kind === "preflight" ? "候选准入预检" : "飞行实验"} · ${labels[run.status] || run.status} · ${run.id}`;
      const meta = document.createElement("small"); meta.textContent = `${run.config?.stack ?? "未知栈"} · started_unix: ${run.started_unix ?? "未返回"} · ${run.run_id ?? "运行身份未返回"}`;
      button.append(meta); button.onclick = () => selectRun(run); $("runs").append(button);
    });
  }
  function renderRun() {
    const run = state.selected; if (!run) { controls(); return; }
    $("run-status").textContent = run.status === "queued" && run.preparation ? "准备可选显示 · 物理尚未启动" : `${run.kind === "preflight" ? "候选准入 / " : ""}${labels[run.status] || run.status}`;
    $("run-identity").textContent = `id: ${run.id}\nrun_id: ${run.run_id ?? "尚未返回"}\nmission_id: ${missionId(run) ?? "尚未返回，不能取消"}`;
    $("directory").textContent = `结果位置：${run.directory ?? "尚未返回"}`;
    const freshness = run.live?.freshness;
    $("live-freshness").textContent = `${({ live: "实时反馈", waiting: "等待反馈", stale: "反馈过期，不可据此判断当前就绪", recorded: "历史记录，不是实时连接" })[freshness?.status] || "尚无新鲜度反馈"}\n${pretty(freshness)}`;
    const publicState = run.live?.state;
    $("live-state").textContent = `连接：${publicState?.connected === true ? "反馈已连接" : publicState?.connected === false ? "反馈未连接" : "未知"} · 定位：${publicState?.odom_valid === true ? "反馈有效（不等于飞行就绪）" : publicState?.odom_valid === false ? "反馈无效" : "未知"}\n${pretty(publicState)}`;
    const control = run.live?.control, mission = run.live?.mission;
    const controlLabel = { 0: "初始化", 1: "RC 位置控制", 2: "命令控制", 3: "降落控制" }[control?.control_state] || "未知";
    $("live-control").textContent = `控制反馈：${controlLabel}\n飞控模式：${publicState?.mode || "未知"} · 安全保护：${control?.failsafe === true ? "已触发" : control?.failsafe === false ? "未触发" : "未知"}\n过期反馈不能证明当前接管。\n\n${pretty(control)}`;
    const missionLabel = { accepted: "任务已受理，尚不代表飞控受理", takeover: "任务报告接管", running: "任务执行中", pausing: "暂停中，等待任务反馈", paused: "任务已暂停派点，物理与飞控继续", resuming: "恢复中，正在请求新的接管", landing: "降落中，等待落地反馈", cancelling: "取消中；暂停时需显式恢复接管后降落", completed: "任务报告完成，以正式结果核对物理", cancelled: "任务已取消，以正式结果核对落地", failed: "任务失败，不表示安全落地" }[mission?.state] || "等待任务反馈";
    const point = mission?.waypoint?.index ?? mission?.index;
    $("live-mission").textContent = `${missionLabel}${point == null ? "" : `\n航点 ${point} / ${run.config?.mission?.waypoints?.length ?? "未知"}`}\n${mission?.event || "尚无任务事件"}\n\n${pretty(mission)}`;
    $("view-status").textContent = pretty(run.view);
    $("phases").textContent = pretty(run.phases);
    $("events").textContent = pretty({ events: run.live?.events ?? null, diagnostics: run.live?.diagnostics ?? null });
    $("run-error").textContent = run.error ? `运行错误：${typeof run.error === "string" ? run.error : pretty(run.error)}` : "";
    controls();
  }
  async function action(fn, target = "config-json", inline = "json-error") {
    if (state.busy) return;
    clearErrors(); state.busy = true; controls();
    try { await fn(); } catch (e) { error(e.message, target, inline); }
    finally { state.busy = false; controls(); }
  }
  function renderSaved() {
    const chosen = $("saved").value; $("saved").replaceChildren(new Option("选择配置", ""));
    state.configs.forEach((entry, i) => $("saved").append(new Option(`${entry.name} · ${entry.revision}`, String(i))));
    $("saved").value = chosen;
  }
  async function bootstrap() {
    if (state.booting) return; state.booting = true;
    $("connection").textContent = "正在连接本地服务…";
    try {
      const data = await api("/api/bootstrap"); if (data.version !== 1 || !data.csrf) throw new Error("不支持的接口版本或缺少 CSRF 令牌。");
      state.csrf = data.csrf; state.defaults = data.defaults; state.configs = data.configs; state.runs = data.runs; state.ue = data.ue_available; state.online = true; state.stopped = false;
      $("data-root").textContent = `数据目录：${data.data_root}`; $("connection").textContent = "本地服务已连接";
      renderSaved(); renderRuns(); if (!state.config) setConfig(data.defaults.px4);
      if (state.selected) { const current = data.runs.find(r => r.id === state.selected.id); if (current) state.selected = current; renderRun(); }
    } catch (e) { state.online = false; $("connection").textContent = `连接失败：${e.message}`; if (!state.runs.length) $("runs").textContent = "无法加载实验列表，请重新连接本地服务。"; }
    finally { state.booting = false; controls(); }
  }
  async function preflight() {
    invalidate(); const config = currentConfig(), edit = state.edit, digest = await hash(config);
    const run = await api("/api/preflight", { config });
    if (!run.id) throw new Error("服务未返回预检身份。");
    if (state.edit === edit) state.ticket = { id: run.id, hash: digest, edit, status: null };
    upsert(run); selectRun(run); ticketNote(run);
  }
  function ticketNote(run) {
    if (state.ticket?.id !== run.id) return;
    const previous = state.ticket.status;
    state.ticket.status = run.status;
    $("preflight-note").textContent = run.status === "pass" ? "候选准入通过，当前配置可申请启动。此结果不代表定位就绪、任务接管或飞行就绪。" : `候选准入：${labels[run.status] || run.status}。${run.error || "等待正式检查结果；不代表飞行就绪。"}`;
    if (run.status === "failed" && previous !== "failed") error(`候选准入失败：${run.error || "请读取原始结果，修正配置后重试。"}`);
  }
  async function evidence(offset = 0) {
    const id = state.selected?.id, stream = $("stream").value;
    const data = await api(`/api/runs/${encodeURIComponent(id)}/evidence?stream=${encodeURIComponent(stream)}&offset=${offset}&limit=50`);
    if (state.selected?.id !== id || $("stream").value !== stream) return;
    state.offset = data.offset; state.total = data.total; state.evidenceLoaded = true;
    $("records").textContent = data.records?.length ? pretty(data.records) : "此记录流为空或缺失，详见诊断。";
    $("diagnostics").textContent = pretty(data.diagnostics); $("page").textContent = `${data.total ? data.offset + 1 : 0}–${Math.min(data.offset + data.records.length, data.total)} / ${data.total}`;
  }
  $("name").addEventListener("input", () => { $("revision").textContent = $("name").value === state.savedName ? `版本 ${state.revision}` : "新名称 · 未保存"; });
  $("stack").addEventListener("change", () => { const stack = $("stack").value; if (state.defaults[stack]) { const mission = state.config.mission == null ? state.config.mission : copy(state.config.mission); const savedName = state.savedName, revision = state.revision, name = $("name").value; setConfig({ ...copy(state.defaults[stack]), mission }, name, revision); state.savedName = savedName; } });
  $("config-json").addEventListener("input", () => { invalidate(); try { state.config = currentConfig(); state.jsonValid = true; $("points-error").textContent = ""; $("stack").value = state.config.stack || ""; renderPoints(); } catch { state.jsonValid = false; $("points-error").textContent = "JSON 尚未有效，任务点编辑暂停。"; $("waypoints").replaceChildren(); $("add-point").disabled = true; } });
  $("apply-json").onclick = () => action(async () => { state.config = currentConfig(); $("stack").value = state.config.stack || ""; renderPoints(); });
  $("add-point").onclick = () => { const points = state.config?.mission?.waypoints; if (!Array.isArray(points) || points.length >= 8) return; points.push({ frame: "enu", position_m: [null, null, null], yaw_rad: null, dwell_s: null }); invalidate(); syncJSON(); renderPoints(); $(`point-${points.length - 1}-frame`).focus(); };
  $("save").onclick = () => action(async () => {
    const name = $("name").value.trim(); if (!/^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(name)) { error("名称须为 1–64 位英文字母、数字、短横线或下划线，并以字母或数字开头。", "name", "name-error"); return; }
    const config = currentConfig(); const saved = await api("/api/configs", { name, config, expected_revision: name === state.savedName ? state.revision : null });
    if (canonical(saved.config) !== canonical(config)) { state.config = copy(saved.config); invalidate(); syncJSON(); renderPoints(); }
    state.configs = state.configs.filter(e => e.name !== saved.name); state.configs.push(saved); state.savedName = saved.name; state.revision = saved.revision; $("name").value = saved.name;
    $("revision").textContent = `版本 ${saved.revision}`; renderSaved(); $("saved").value = String(state.configs.length - 1); $("save-note").textContent = `已保存 ${saved.name} · ${saved.revision}。未启动飞行。`;
  });
  $("reload").onclick = () => action(async () => { const entry = state.configs[Number($("saved").value)]; if ($("saved").value === "" || !entry) throw new Error("请先选择已保存配置。"); const data = await api("/api/bootstrap"); state.csrf = data.csrf; state.configs = data.configs; const latest = data.configs.find(c => c.name === entry.name); if (!latest) throw new Error("所选配置已不存在，请刷新列表。"); setConfig(latest.config, latest.name, latest.revision); renderSaved(); $("save-note").textContent = `已重载 ${latest.name} · ${latest.revision}，请重新预检。`; });
  $("preflight").onclick = () => action(preflight);
  $("start").onclick = () => action(async () => {
    const config = currentConfig(), ticket = state.ticket;
    if (!ticket || ticket.status !== "pass" || ticket.edit !== state.edit || await hash(config) !== ticket.hash) { invalidate(); throw new Error("配置与通过的预检不一致，请重新预检。"); }
    const run = await api("/api/start", { config, preflight_id: ticket.id, with_view: $("with-view").checked });
    if (!run.id) throw new Error("服务未返回实验身份。"); state.ticket = null; $("preflight-note").textContent = "启动请求已返回运行身份。再次启动需重新预检；请观察实际任务反馈。"; upsert(run); selectRun(run);
  });
  $("cancel").onclick = () => { const run = state.selected; state.cancelTarget = { id: run.id, mission: missionId(run) }; $("cancel-target").textContent = `实验：${run.id}\n任务：${missionId(run)}`; $("cancel-dialog").showModal(); };
  $("cancel-back").onclick = () => $("cancel-dialog").close();
  $("cancel-confirm").onclick = () => { $("cancel-dialog").close(); action(async () => { const target = state.cancelTarget; const latest = await api(`/api/runs/${encodeURIComponent(target.id)}`); if (!active(latest) || missionId(latest) !== target.mission) throw new Error("任务身份或状态已变化，请重新确认。"); const response = await api(`/api/runs/${encodeURIComponent(target.id)}/cancel`, { mission_id: target.mission }); $("cancel-note").textContent = `${target.id}：${response.submitted ? "取消请求已受理，尚未确认落地。" : "未确认请求受理。"}\n${pretty(response)}`; }, "cancel", "run-error"); };
  for (const name of ["open", "close"]) $("view-" + name).onclick = () => action(async () => { const id = state.selected.id; const view = await api(`/api/runs/${encodeURIComponent(id)}/view`, { action: name }); if (state.selected?.id === id) { state.selected.view = view; renderRun(); } }, "view-" + name, "run-error");
  $("load-result").onclick = () => action(async () => { const id = state.selected.id, result = await api(`/api/runs/${encodeURIComponent(id)}/result`); if (state.selected?.id === id) { state.selected.result = result.values; $("result").textContent = `原文 SHA-256: ${result.sha256}\n格式诊断: ${pretty(result.diagnostics)}\n\n${result.raw_json}`; $("result-details").open = true; renderRun(); } }, "load-result", "evidence-error");
  $("load-evidence").onclick = () => action(() => evidence(), "load-evidence", "evidence-error");
  $("prev").onclick = () => action(() => evidence(Math.max(0, state.offset - 50)), "load-evidence", "evidence-error");
  $("next").onclick = () => action(() => evidence(state.offset + 50), "load-evidence", "evidence-error");
  $("stream").onchange = () => { resetEvidence(); controls(); };
  $("refresh-runs").onclick = () => action(async () => { state.runs = (await api("/api/runs")).runs; renderRuns(); }, "refresh-runs", "run-error");
  $("reconnect").onclick = bootstrap;
  $("shutdown").onclick = () => $("shutdown-dialog").showModal(); $("shutdown-back").onclick = () => $("shutdown-dialog").close();
  $("shutdown-confirm").onclick = () => { $("shutdown-dialog").close(); action(async () => { const result = await api("/api/shutdown", {}); if (result.stopping) { state.stopped = true; state.online = false; $("connection").textContent = "服务正在关闭"; } }, "shutdown", "run-error"); };
  async function poll() {
    if (state.online && !state.stopped && !state.booting) {
      try {
        state.runs = (await api("/api/runs")).runs;
        const ids = [...new Set([state.selected?.id, state.ticket?.id].filter(Boolean))];
        const results = await Promise.all(ids.map(id => api(`/api/runs/${encodeURIComponent(id)}`)));
        for (const run of results) { upsert(run); ticketNote(run); if (run.id === state.selected?.id) state.selected = run; }
        renderRun(); renderRuns(); $("connection").textContent = "本地服务已连接 · 状态轮询 750 ms";
      } catch (e) { state.online = false; $("connection").textContent = `连接中断：${e.message}；显示的是最后反馈，请重新连接。`; $("live-freshness").textContent = "服务连接中断，当前状态不可验证。以下各项保留最后一次反馈。"; controls(); }
    }
    setTimeout(poll, 750);
  }
  for (const action of ["pause", "resume"]) $("mission-" + action).onclick = () => openMissionAction(action);
  $("mission-action-confirm").onclick = submitMissionAction;
  $("mission-action-back").onclick = () => $("mission-action-dialog").close();
  $("mission-action-dialog").addEventListener("cancel", () => invalidateActionDialog("已返回观察，未提交的确认已失效。"));
  $("mission-action-dialog").addEventListener("close", () => {
    const origin = actionDialog?.frozen.action; actionDialog = null; controls();
    const button = $("mission-" + (origin || "pause"));
    if (!button.disabled) button.focus(); else $("mission-action-note").focus();
  });
  window.addEventListener("offline", () => { state.online = false; controls(); });
  setInterval(renderMissionActions, 250);
  $("name").setAttribute("aria-describedby", "name-error");
  bootstrap(); setTimeout(poll, 750);
})();
