// Offline Node VM tests with a minimal DOM double. NOT browser acceptance.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { test } from 'node:test';

const source = readFileSync(new URL('../Simulator/wksim_console/web/app.js', import.meta.url), 'utf8');
const html = readFileSync(new URL('../Simulator/wksim_console/web/index.html', import.meta.url), 'utf8');
function harness() {
  const elements = new Map();
  let now = 10000;
  const document = {
    activeElement: null, querySelectorAll: () => [],
    getElementById(id) { assert.ok(elements.has(id), `missing HTML element ${id}`); return elements.get(id); },
    createElement: () => element(),
  };
  function element() {
    const listeners = new Map();
    return { textContent: '', value: '', disabled: false, open: false, attrs: {},
      setAttribute(k, v) { this.attrs[k] = v; }, removeAttribute(k) { delete this.attrs[k]; },
      addEventListener(k, fn) { listeners.set(k, fn); },
      append() {}, replaceChildren() {}, closest() { return null; },
      focus() { document.activeElement = this; },
      showModal() { this.open = true; },
      close() { this.open = false; listeners.get('close')?.(); },
      fire(k) { listeners.get(k)?.(); },
    };
  }
  for (const [, id] of html.matchAll(/\bid="([^"]+)"/g)) elements.set(id, element());
  const listeners = new Map(), calls = [];
  let reply = async () => { throw new Error('unexpected fetch'); };
  const context = vm.createContext({ document, navigator: { onLine: true },
    window: { addEventListener: (k, fn) => listeners.set(k, fn) },
    Date: { now: () => { throw new Error('wall clock used for freshness'); } }, performance: { now: () => now }, AbortSignal, TextEncoder, console,
    setInterval() {}, setTimeout() {}, Option: function () { return element(); },
    fetch: async (path, options) => { calls.push({ path, options }); return reply(path, options); },
  });
  const instrumented = source.replace('bootstrap(); setTimeout(poll, 750);',
    'globalThis.t = {state, controls, selectRun, openMissionAction, submitMissionAction, observeActionFeedback, actionRecords, detailTimes, api, renderRun, renderMissionActions, getDialog: () => actionDialog};');
  assert.notEqual(instrumented, source);
  vm.runInContext(instrumented, context);
  const t = context.t;
  t.state.online = true; t.state.csrf = 'csrf-original';
  function run(action = 'pause') {
    return { id: 'job-1', run_id: 'run-1', kind: 'flight', status: 'running',
      live: { freshness: { status: 'live' }, action_offer: { version: 1, mission_id: 'mission-1',
        action_token: 'token-1', control_epoch: 'epoch-1', native_generation: 4, allowed_actions: [action], reason: 'available' },
        mission: { run_id: 'run-1', mission_id: 'mission-1', state: 'running' }, events: [] } };
  }
  function select(r = run()) { t.detailTimes.set(r, now); t.selectRun(r); return r; }
  function request(target = t.getDialog().frozen, id = 'request-1') {
    const { version, run_id, mission_id, control_epoch, native_generation, action_token, action } = target;
    return { version, run_id, mission_id, control_epoch, native_generation, action_token, request_id: id, action };
  }
  function feedback(r, req, event, stream = 'mission') {
    const payload = { run_id: r.run_id, mission_id: req.mission_id, control_epoch: req.control_epoch,
      native_generation: req.native_generation, event, state: 'paused',
      action_request: req, pause: { pause_request: req, resume_request: req } };
    r.live.events = [{ stream, payload }]; t.observeActionFeedback(r); t.renderMissionActions();
  }
  return { t, calls, elements, run, select, request, feedback, context,
    el: id => elements.get(id), advance: ms => { now += ms; t.renderMissionActions(); },
    offline: () => listeners.get('offline')(),
    respond: fn => { reply = async (path, options) => ({ ok: true, json: async () => fn(path, options) }); },
    rejectPost: (r, status) => { reply = async (path, options) => ({ ok: options.method === 'GET', status,
      json: async () => options.method === 'GET' ? structuredClone(r) : {error: 'offer is stale'} }); },
    reject: () => { reply = async () => { throw new Error('response lost'); }; },
  };
}

test('HTML hooks, native dialog semantics and unchanged basic actions exist', () => {
  const h = harness();
  for (const id of ['save', 'preflight', 'start', 'cancel', 'view-open', 'view-close', 'load-result', 'load-evidence']) assert.equal(typeof h.el(id).onclick, 'function');
  assert.match(html, /<dialog id="mission-action-dialog"[^>]+aria-describedby=/);
  assert.match(html, /BODY.*ENU/);
  assert.match(html, /取消不会自动抢回控制/);
});

test('only detailed, live, online running flights with one valid offer enable action', () => {
  const h = harness(); h.select(); assert.equal(h.el('mission-pause').disabled, false);
  assert.equal(h.el('mission-resume').disabled, true);
  const changes = [r => r.kind = 'preflight', r => r.status = 'queued', r => r.live.freshness.status = 'stale',
    r => r.live.action_offer.version = 2, r => r.live.action_offer.allowed_actions = [],
    r => r.live.action_offer.allowed_actions = ['pause', 'resume'], r => delete r.live.action_offer,
    r => r.live.action_offer.native_generation = null, r => r.live.action_offer.native_generation = 2 ** 53,
    r => r.live.action_offer.action_token = '', r => r.run_id = null];
  for (const change of changes) { const r = h.run(); change(r); h.select(r); assert.equal(h.el('mission-pause').disabled, true); }
  h.t.selectRun(h.run()); assert.equal(h.el('mission-pause').disabled, true, 'list-only data cannot authorize');
  h.select(); h.offline(); assert.equal(h.el('mission-pause').disabled, true);
});

test('pause/resume submit exact frozen five-field bodies and original CSRF, HTTP success is not confirmation', async () => {
  for (const action of ['pause', 'resume']) {
    const h = harness(), r = h.select(h.run(action)); h.t.openMissionAction(action);
    assert.ok(Object.isFrozen(h.t.getDialog().frozen));
    assert.equal(h.context.document.activeElement, h.el('mission-action-back'));
    const req = h.request();
    h.respond((path, options) => options.method === 'GET' ? structuredClone(r) : { submitted: true, request: req });
    const first = h.t.submitMissionAction(); const duplicate = h.t.submitMissionAction();
    assert.equal(h.el('mission-action-confirm').attrs['aria-busy'], 'true');
    await Promise.all([first, duplicate]);
    assert.equal(h.calls.length, 2);
    assert.deepEqual(JSON.parse(h.calls[1].options.body), { mission_id: 'mission-1', action_token: 'token-1', action, control_epoch: 'epoch-1', native_generation: 4 });
    assert.equal(h.calls[1].options.headers['X-Wksim-CSRF'], 'csrf-original');
    assert.match(h.el('mission-action-note').textContent, /文件已提交/);
    assert.doesNotMatch(h.el('mission-action-note').textContent, /已匹配/);
    h.t.openMissionAction(action); await h.t.submitMissionAction(); assert.equal(h.calls.length, 2);
  }
});

test('selection, offline, local timeout and stale state permanently invalidate open dialogs', async () => {
  for (const change of [h => h.t.selectRun(h.run()), h => h.offline(), h => h.advance(2501),
    h => { h.t.state.selected.live.freshness.status = 'stale'; h.t.controls(); }]) {
    const h = harness(); h.select(); h.t.openMissionAction('pause');
    h.el('mission-action-confirm').focus(); change(h);
    assert.equal(h.el('mission-action-confirm').disabled, true);
    await h.t.submitMissionAction(); assert.equal(h.calls.length, 0);
    assert.equal(h.t.getDialog().invalid, true);
  }
});

test('revalidation refuses all changed identities or withdrawn offers without POST', async () => {
  const changes = [r => r.id = 'other-job', r => r.run_id = 'other-run', r => r.kind = 'preflight', r => r.status = 'pass',
    ...['mission_id', 'control_epoch', 'action_token'].map(k => r => r.live.action_offer[k] += '-new'),
    r => r.live.action_offer.native_generation++, r => r.live.action_offer.allowed_actions = [], r => r.live.freshness.status = 'stale'];
  for (const change of changes) {
    const h = harness(), r = h.select(); h.t.openMissionAction('pause');
    const latest = structuredClone(r); change(latest); h.respond(() => latest);
    await h.t.submitMissionAction(); assert.equal(h.calls.length, 1); assert.equal(h.t.getDialog().invalid, true);
  }
});

test('selection change or Escape during pending GET prevents submission', async () => {
  for (const dismiss of [h => h.t.selectRun(h.run()), h => h.el('mission-action-dialog').close()]) {
    const h = harness(), r = h.select(); h.t.openMissionAction('pause');
    let resolve; h.respond(() => new Promise(done => { resolve = done; }));
    const pending = h.t.submitMissionAction(); await new Promise(done => setImmediate(done)); dismiss(h); resolve(r);
    await pending; assert.equal(h.calls.length, 1);
  }
});

test('response loss retains unknown token record and never retries after reconnect/reselection', async () => {
  const h = harness(), r = h.select(); h.t.openMissionAction('pause');
  h.respond((path, options) => { if (options.method === 'GET') return structuredClone(r); throw new Error('response lost'); });
  await h.t.submitMissionAction(); assert.equal(h.t.actionRecords.size, 1);
  assert.match(h.el('mission-action-note').textContent, /结果未知/);
  h.el('mission-action-dialog').close(); h.select(r); h.t.openMissionAction('pause'); await h.t.submitMissionAction();
  assert.equal(h.calls.length, 2);
  const record = [...h.t.actionRecords.values()][0]; h.feedback(r, h.request(record.target), 'mission_paused');
  assert.equal(record.feedback, undefined); assert.match(h.el('mission-action-note').textContent, /结果未知/);
});

test('explicit HTTP rejection is distinct from response loss or server failure', async () => {
  for (const status of [400, 403, 404, 500]) {
    const h = harness(), r = h.select(); h.t.openMissionAction('pause'); h.rejectPost(r, status);
    await h.t.submitMissionAction();
    assert.match(h.el('mission-action-note').textContent, status === 500 ? /结果未知/ : /服务已拒绝请求/);
    h.el('mission-action-dialog').close(); h.select(r); h.t.openMissionAction('pause');
    await h.t.submitMissionAction(); assert.equal(h.calls.length, 2);
  }
});

test('feedback requires stream, event, full request identity and request_id; received is not completed', async () => {
  for (const action of ['pause', 'resume']) {
    const h = harness(), r = h.select(h.run(action)); h.t.openMissionAction(action); const req = h.request();
    h.respond((path, options) => options.method === 'GET' ? r : { submitted: true, request: req }); await h.t.submitMissionAction();
    const record = [...h.t.actionRecords.values()][0], event = action === 'pause' ? 'mission_paused' : 'mission_resumed';
    for (const field of ['mission_id', 'run_id', 'control_epoch', 'native_generation', 'action_token', 'request_id', 'action']) {
      h.feedback(r, { ...req, [field]: 'wrong' }, event); assert.equal(record.feedback, undefined, field);
    }
    h.feedback(r, req, event, 'telemetry'); assert.equal(record.feedback, undefined);
    h.feedback(r, req, 'paused'); assert.equal(record.feedback, undefined);
    h.feedback(r, req, action === 'pause' ? 'mission_pausing' : 'mission_resume_received');
    assert.match(h.el('mission-action-note').textContent, /受理反馈，等待动作确认/);
    r.live.action_offer.action_token = 'rotated'; h.feedback(r, req, event);
    assert.equal(record.feedback, event); assert.equal(record.invalid, true);
    assert.match(h.el('mission-action-note').textContent, /已匹配该请求的任务确认反馈/);
  }
});

test('current mission progress confirms via nested request; wrong HTTP response stays unknown', async () => {
  const h = harness(), r = h.select(); h.t.openMissionAction('pause'); const req = h.request();
  h.respond((path, options) => options.method === 'GET' ? r : { submitted: true, request: req }); await h.t.submitMissionAction();
  r.live.mission = { run_id: r.run_id, mission_id: req.mission_id, control_epoch: req.control_epoch,
    native_generation: req.native_generation + 1, event: 'mission_paused', pause: { pause_request: req } };
  h.t.observeActionFeedback(r); assert.equal([...h.t.actionRecords.values()][0].feedback, undefined);
  r.live.mission.native_generation = req.native_generation;
  h.t.observeActionFeedback(r); assert.equal([...h.t.actionRecords.values()][0].feedback, 'mission_paused');
  const bad = harness(), br = bad.select(); bad.t.openMissionAction('pause');
  bad.respond((path, options) => options.method === 'GET' ? br : { submitted: true, request: { ...bad.request(), control_epoch: 'new' } });
  await bad.t.submitMissionAction(); assert.match(bad.el('mission-action-note').textContent, /结果未知/);
});
