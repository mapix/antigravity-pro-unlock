const { test } = require('node:test');
const assert = require('node:assert/strict');
const bridge = require('../skills/antigravity-pro-unlock/scripts/carbon_modes_bridge.js');
const { wireField: f, concat: join, parseWire: parse } = bridge;
const source = () => ({ clientModelConfigs: [{ label: 'Orchestrator (Carbon) (Gateway)',
  modelId: 'gemini-4-carbon', modelOrAlias: { model: 'MODEL_PLACEHOLDER_M349' }, supportsImages: true }],
  clientModelSorts: [{ name: 'Recommended', groups: [{ groupName: 'Enterprise Models',
    modelLabels: ['Orchestrator (Carbon) (Gateway)'] }] }],
  defaultOverrideModelConfig: { modelOrAlias: { model: 'MODEL_PLACEHOLDER_M349' } } });
test('catalog gives direct mode a distinct native identity and retains defaults and capabilities', () => {
  const original = source(), result = bridge.catalogJson(original);
  assert.equal(result.registered, true);
  assert.equal(original.clientModelConfigs.length, 1);
  assert.equal(result.data.clientModelConfigs[0].modelOrAlias.model, 326);
  assert.equal(result.data.clientModelConfigs[0].supportsImages, true);
  assert.deepEqual(result.data.defaultOverrideModelConfig, original.defaultOverrideModelConfig);
  assert.deepEqual(result.data.clientModelSorts[0].groups[0].modelLabels,
    [bridge.DIRECT_LABEL, 'Orchestrator (Carbon) (Gateway)']);
  assert.equal(bridge.catalogJson(result.data).data.clientModelConfigs.length, 2);
  original.clientModelConfigs[0].disabled = true;
  assert.equal(bridge.catalogJson(original).registered, false);
});
test('request augmentation is per request and preserves other models and explicit BYOM overrides', () => {
  const direct = { cascadeId: 'own', cascadeConfig: { plannerConfig: { planModel: 326 } } };
  const patched = bridge.requestJson('SendUserCascadeMessage', direct);
  assert.equal(patched.cascadeConfig.plannerConfig.customModelInfoOverride.modelName, 'gemini-4-carbon');
  assert.equal(direct.cascadeConfig.plannerConfig.customModelInfoOverride, undefined);
  const orchestrator = { cascadeConfig: { plannerConfig: { planModel: 349 } } };
  assert.equal(bridge.requestJson('SendUserCascadeMessage', orchestrator), orchestrator);
  const supplied = { cascadeConfig: { plannerConfig: { planModel: 326,
    customModelInfoOverride: { modelName: 'user-custom-model' } } } };
  assert.equal(bridge.requestJson('SendUserCascadeMessage', supplied), supplied);
});
test('binary request retains unknown fields while adding only the native ModelInfo override', () => {
  const planner = join([f(1, 0, 326), f(99, 2, 'unknown-planner')]);
  const config = join([f(1, 2, planner), f(77, 0, 123)]);
  const request = join([f(1, 2, 'session'), f(5, 2, config), f(101, 2, 'unknown-request')]);
  const changed = parse(bridge.requestWire('SendUserCascadeMessage', request));
  assert.deepEqual(changed.find(x => x.number === 101).raw, parse(request).find(x => x.number === 101).raw);
  const cfg = parse(changed.find(x => x.number === 5).value);
  assert.equal(Number(cfg.find(x => x.number === 77).value), 123);
  const pc = parse(cfg.find(x => x.number === 1).value);
  assert.equal(Number(pc.find(x => x.number === 1).value), 326);
  assert.equal(new TextDecoder().decode(pc.find(x => x.number === 99).value), 'unknown-planner');
  const info = parse(pc.find(x => x.number === 27).value);
  assert.equal(new TextDecoder().decode(info.find(x => x.number === 8).value), 'gemini-4-carbon');
  assert.deepEqual(bridge.requestWire('SendUserCascadeMessage', bridge.requestWire('SendUserCascadeMessage', request)),
    bridge.requestWire('SendUserCascadeMessage', request));
});
test('binary catalog adds matching row and sort label without losing opaque fields', () => {
  const row = join([f(1, 2, 'Orchestrator (Carbon) (Gateway)'), f(2, 2, f(1, 0, 349)),
    f(21, 2, 'gemini-4-carbon'), f(100, 2, 'capability-data')]);
  const group = join([f(1, 2, 'Enterprise Models'), f(2, 2, 'Orchestrator (Carbon) (Gateway)')]);
  const sort = join([f(1, 2, 'Recommended'), f(2, 2, group)]);
  const result = bridge.catalogWire(join([f(1, 2, row), f(2, 2, sort), f(99, 0, 42)]));
  assert.equal(result.registered, true);
  const top = parse(result.bytes), rows = top.filter(x => x.number === 1);
  assert.equal(rows.length, 2);
  assert.deepEqual(parse(rows[0].value).find(x => x.number === 100).raw, parse(row).find(x => x.number === 100).raw);
  assert.equal(Number(top.find(x => x.number === 99).value), 42);
  assert.equal(bridge.catalogWire(result.bytes).bytes, result.bytes);
});
test('actual UI GetUserStatus hydration carries the catalog while retaining account fields', () => {
  const account = { userStatus: { pro: false, email: 'test@example.com', cascadeModelConfigData: source() },
    planInfo: { unchanged: true } };
  const changed = bridge.statusJson(account);
  assert.equal(changed.registered, true);
  assert.equal(changed.data.userStatus.pro, false);
  assert.equal(changed.data.userStatus.email, account.userStatus.email);
  assert.equal(changed.data.planInfo, account.planInfo);
  const row = join([f(1, 2, 'Orchestrator (Carbon) (Gateway)'), f(2, 2, f(1, 0, 349)),
    f(21, 2, 'gemini-4-carbon')]);
  const status = join([f(1, 0, 0), f(7, 2, 'test@example.com'), f(33, 2, f(1, 2, row))]);
  const binary = bridge.statusWire(join([f(1, 2, status), f(2, 2, 'opaque-plan-info')]));
  assert.equal(binary.registered, true);
  const parsed = parse(binary.bytes);
  assert.deepEqual(parsed.find(x => x.number === 2).raw, f(2, 2, 'opaque-plan-info'));
  const parsedStatus = parse(parsed.find(x => x.number === 1).value);
  assert.equal(Number(parsedStatus.find(x => x.number === 1).value), 0);
  assert.equal(parse(parsedStatus.find(x => x.number === 33).value).filter(x => x.number === 1).length, 2);
});
test('Hub HTTP fallback gRPC-web JSON frames preserve trailers and unrelated fields', () => {
  const frame = (flag, value) => {
    const body = new TextEncoder().encode(value), header = new Uint8Array(5); header[0] = flag;
    new DataView(header.buffer).setUint32(1, body.length); return join([header, body]);
  };
  const trailers = frame(128, 'grpc-status: 0\r\n');
  const body = join([frame(0, JSON.stringify({ userStatus: { pro: false, cascadeModelConfigData: source() } })), trailers]);
  const changed = bridge.mapBody('application/grpc-web+json', body,
    value => bridge.statusJson(value).data, value => value);
  const size = new DataView(changed.buffer, changed.byteOffset + 1, 4).getUint32(0);
  const status = JSON.parse(new TextDecoder().decode(changed.slice(5, 5 + size)));
  assert.equal(status.userStatus.cascadeModelConfigData.clientModelConfigs.length, 2);
  assert.equal(status.userStatus.pro, false);
  assert.deepEqual(changed.slice(5 + size), trailers);
});
test('fetch bridge keeps session modes independent and leaves unrelated origins untouched', async () => {
  const received = [];
  const root = { document: {}, location: { origin: 'https://127.0.0.1:1234', hostname: '127.0.0.1',
      href: 'https://127.0.0.1:1234/c/session?project=keep&wsTransport=3' },
    history: { state: { keep: true }, replaceState(state, unused, url) { this.last = { state, url }; } },
    __APP_CONFIG__: { appVersion: '2.31.2', productName: 'antigravity' },
    fetch: async (input, init) => {
      const req = new Request(input, init); received.push(req);
      return req.url.endsWith('GetCascadeModelConfigData')
        ? new Response(JSON.stringify(source()), { headers: { 'content-type': 'application/json' } })
        : new Response('{}', { headers: { 'content-type': 'application/json' } });
    } };
  root.top = root.self = root;
  const api = bridge.install(root);
  assert.equal(new URL(root.history.last.url).searchParams.get('project'), 'keep');
  assert.equal(new URL(root.history.last.url).searchParams.get('useWebSocket'), 'false');
  assert.deepEqual(root.history.last.state, { keep: true });
  const url = root.location.origin + '/exa.language_server_pb.LanguageServerService/';
  const catalog = await (await root.fetch(url + 'GetCascadeModelConfigData', { method: 'POST', body: '{}' })).json();
  assert.equal(catalog.clientModelConfigs.length, 2);
  assert.equal(api.isReady(), true);
  for (const [id, model] of [['direct-session', 326], ['orchestrator-session', 349]]) {
    await root.fetch(url + 'SendUserCascadeMessage', { method: 'POST', headers: { 'content-type': 'application/json',
      'x-codeium-csrf-token': 'test-only' }, body: JSON.stringify({ cascadeId: id,
      cascadeConfig: { plannerConfig: { planModel: model } } }) });
  }
  const direct = await received[1].json(), orchestrator = await received[2].json();
  assert.equal(direct.cascadeId, 'direct-session');
  assert.equal(direct.cascadeConfig.plannerConfig.customModelInfoOverride.modelName, 'gemini-4-carbon');
  assert.equal(received[1].headers.get('x-codeium-csrf-token'), 'test-only');
  assert.equal(orchestrator.cascadeConfig.plannerConfig.customModelInfoOverride, undefined);
  await root.fetch('https://example.com/anything', { method: 'POST', body: 'unrelated' });
  assert.equal(await received.at(-1).text(), 'unrelated');
});
