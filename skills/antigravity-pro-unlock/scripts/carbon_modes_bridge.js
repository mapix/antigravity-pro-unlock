/* Antigravity desktop selector adapter for inspected releases. */
(function (root, factory) {
  const api = factory();
  if (typeof window === 'object' && window.document) api.install(root);
  else if (typeof module === 'object') module.exports = api;
})(globalThis, function () {
  'use strict';
  const VERSION = '1.5.0';
  const SERVICE = '/exa.language_server_pb.LanguageServerService/';
  const DIRECT_ID = 'antigravity-pro-unlock-carbon-direct';
  const DIRECT_LABEL = 'Gemini 4 Carbon (Direct) (Gateway)';
  const SOURCE_LABEL = 'Orchestrator (Carbon) (Gateway)';
  const BYOM = 326;
  const CARBON = 349;
  const CARBON_233 = 437;
  const CARBON_BY_VERSION = Object.freeze({ '2.31.2': CARBON, '2.33.0': CARBON_233 });
  const MODEL_INFO = Object.freeze({
    modelId: BYOM, modelName: 'gemini-4-carbon', chatModelName: 'gemini-4-carbon',
    apiProvider: 24, modelProvider: 4, maxTokens: 1048576, maxOutputTokens: 65536,
    supportsContext: true, displayName: DIRECT_LABEL,
  });
  const CONFIG_FIELDS = Object.freeze({
    SendUserCascadeMessage: ['cascadeConfig', 5],
    SendAllQueuedMessages: ['cascadeConfig', 3],
    GetTokenBase: ['cascadeConfig', 1],
    GetSlashCommands: ['cascadeConfig', 1],
    RevertToCascadeStep: ['overrideConfig', 5],
  });
  const encoder = new TextEncoder();
  const decoder = new TextDecoder('utf-8', { fatal: true });
  const clone = value => JSON.parse(JSON.stringify(value));
  function enumValue(value) {
    if (typeof value === 'number') return value;
    if (value === 'MODEL_GOOGLE_GEMINI_INTERNAL_BYOM') return BYOM;
    if (value === 'MODEL_GOOGLE_JARVIS_V4S') return CARBON;
    const match = /^MODEL_PLACEHOLDER_M(\d+)$/.exec(value || '');
    return match ? Number(match[1]) : undefined;
  }
  function catalogJson(data, carbon = CARBON) {
    const source = data.clientModelConfigs?.find(row => row.modelId === 'gemini-4-carbon'
      && row.label === SOURCE_LABEL && enumValue(row.modelOrAlias?.model) === carbon && !row.disabled);
    if (!source) return { data, registered: false };
    if (data.clientModelConfigs.some(row => row.modelId === DIRECT_ID)) return { data, registered: true };
    const next = clone(data);
    const index = next.clientModelConfigs.findIndex(row => row.modelId === source.modelId);
    next.clientModelConfigs.splice(index, 0, {
      ...clone(source), label: DIRECT_LABEL, modelId: DIRECT_ID, modelOrAlias: { model: BYOM },
    });
    let placed = false;
    for (const sort of next.clientModelSorts || []) for (const group of sort.groups || []) {
      const at = group.modelLabels?.indexOf(SOURCE_LABEL) ?? -1;
      if (at >= 0 && !group.modelLabels.includes(DIRECT_LABEL)) {
        group.modelLabels.splice(at, 0, DIRECT_LABEL); placed = true;
      }
    }
    if (!placed) (next.clientModelSorts ||= []).push({ name: 'Local modes',
      groups: [{ groupName: 'Enterprise Models', modelLabels: [DIRECT_LABEL, SOURCE_LABEL] }] });
    return { data: next, registered: true };
  }
  function requestJson(method, data, checkpointLimit) {
    const field = CONFIG_FIELDS[method]?.[0];
    const planner = field && data[field]?.plannerConfig;
    if (!planner || enumValue(planner.planModel) !== BYOM || planner.customModelInfoOverride != null) return data;
    const next = clone(data);
    next[field].plannerConfig.customModelInfoOverride = clone(MODEL_INFO);
    if (checkpointLimit && next[field].checkpointConfig?.maxTokenLimit == null) {
      (next[field].checkpointConfig ||= {}).maxTokenLimit = checkpointLimit;
    }
    return next;
  }
  function statusJson(data, carbon = CARBON) {
    if (!data.userStatus?.cascadeModelConfigData) return { data, registered: false };
    const result = catalogJson(data.userStatus.cascadeModelConfigData, carbon);
    return { data: result.registered ? { ...data, userStatus: { ...data.userStatus,
      cascadeModelConfigData: result.data } } : data, registered: result.registered };
  }
  function concat(parts) {
    const result = new Uint8Array(parts.reduce((n, bytes) => n + bytes.length, 0));
    let offset = 0;
    for (const bytes of parts) { result.set(bytes, offset); offset += bytes.length; }
    return result;
  }
  function varint(value) {
    let n = BigInt(value); const out = [];
    do { let byte = Number(n & 127n); n >>= 7n; out.push(byte | (n ? 128 : 0)); } while (n);
    return Uint8Array.from(out);
  }
  function wireField(number, wire, value) {
    const bytes = wire === 2 ? (typeof value === 'string' ? encoder.encode(value) : value) : varint(value);
    return concat([varint(number * 8 + wire), ...(wire === 2 ? [varint(bytes.length)] : []), bytes]);
  }
  function parseWire(bytes) {
    let at = 0;
    const read = () => {
      let value = 0n;
      for (let shift = 0n; shift < 70n; shift += 7n) {
        if (at >= bytes.length) throw Error('Truncated protobuf');
        const byte = bytes[at++]; value |= BigInt(byte & 127) << shift;
        if (!(byte & 128)) return value;
      }
      throw Error('Invalid protobuf varint');
    };
    const fields = [];
    while (at < bytes.length) {
      const start = at, tag = Number(read()), number = tag >>> 3, wire = tag & 7;
      if (!number) throw Error('Invalid protobuf tag');
      let value;
      if (wire === 0) value = read();
      else if (wire === 2) { const size = Number(read()); value = bytes.slice(at, at + size); at += size; }
      else if (wire === 1 || wire === 5) { const size = wire === 1 ? 8 : 4; value = bytes.slice(at, at + size); at += size; }
      else throw Error('Unsupported protobuf wire type');
      if (at > bytes.length) throw Error('Truncated protobuf field');
      fields.push({ number, wire, value, raw: bytes.slice(start, at) });
    }
    return fields;
  }
  const fieldValue = (fields, number) => fields.find(field => field.number === number)?.value;
  function replaceWire(fields, changes) {
    const seen = new Set(); const result = [];
    for (const field of fields) {
      if (changes.has(field.number)) {
        if (!seen.has(field.number)) result.push(changes.get(field.number));
        seen.add(field.number);
      } else result.push(field.raw);
    }
    for (const [number, raw] of changes) if (!seen.has(number)) result.push(raw);
    return concat(result);
  }
  function modelInfoWire() {
    return concat([wireField(1, 0, BYOM), wireField(4, 0, MODEL_INFO.maxTokens),
      wireField(7, 0, MODEL_INFO.apiProvider), wireField(8, 2, MODEL_INFO.modelName),
      wireField(9, 0, 1), wireField(12, 2, MODEL_INFO.chatModelName),
      wireField(13, 0, MODEL_INFO.maxOutputTokens), wireField(20, 2, DIRECT_LABEL),
      wireField(24, 0, MODEL_INFO.modelProvider)]);
  }
  function requestWire(method, bytes, checkpointLimit) {
    const number = CONFIG_FIELDS[method]?.[1];
    if (!number) return bytes;
    const top = parseWire(bytes), configBytes = fieldValue(top, number);
    if (!(configBytes instanceof Uint8Array)) return bytes;
    const config = parseWire(configBytes), plannerBytes = fieldValue(config, 1);
    if (!(plannerBytes instanceof Uint8Array)) return bytes;
    const planner = parseWire(plannerBytes);
    if (Number(fieldValue(planner, 1)) !== BYOM || planner.some(field => field.number === 27)) return bytes;
    const nextPlanner = concat([...planner.map(field => field.raw), wireField(27, 2, modelInfoWire())]);
    const changes = new Map([[1, wireField(1, 2, nextPlanner)]]);
    if (checkpointLimit) {
      const checkpoint = parseWire(fieldValue(config, 2) || new Uint8Array());
      if (!checkpoint.some(field => field.number === 5)) {
        changes.set(2, wireField(2, 2, concat([
          ...checkpoint.map(field => field.raw), wireField(5, 0, checkpointLimit),
        ])));
      }
    }
    const nextConfig = replaceWire(config, changes);
    return replaceWire(top, new Map([[number, wireField(number, 2, nextConfig)]]));
  }
  function catalogWire(bytes, carbon = CARBON) {
    const top = parseWire(bytes);
    const text = (fields, number) => { const value = fieldValue(fields, number); return value ? decoder.decode(value) : ''; };
    let source, existing = false;
    for (const field of top.filter(field => field.number === 1 && field.wire === 2)) {
      const row = parseWire(field.value), id = text(row, 21);
      if (id === DIRECT_ID) existing = true;
      if (id === 'gemini-4-carbon' && text(row, 1) === SOURCE_LABEL && !fieldValue(row, 4)) {
        const alias = fieldValue(row, 2);
        if (alias && Number(fieldValue(parseWire(alias), 1)) === carbon) source = field;
      }
    }
    if (!source) return { bytes, registered: false };
    if (existing) return { bytes, registered: true };
    const row = replaceWire(parseWire(source.value), new Map([[1, wireField(1, 2, DIRECT_LABEL)],
      [2, wireField(2, 2, wireField(1, 0, BYOM))], [21, wireField(21, 2, DIRECT_ID)]]));
    let placed = false; const output = [];
    for (const field of top) {
      if (field === source) output.push(wireField(1, 2, row));
      if (field.number !== 2 || field.wire !== 2) { output.push(field.raw); continue; }
      const sort = parseWire(field.value), sortOutput = [];
      for (const groupField of sort) {
        if (groupField.number !== 2 || groupField.wire !== 2) { sortOutput.push(groupField.raw); continue; }
        const group = parseWire(groupField.value), labels = group.filter(f => f.number === 2 && f.wire === 2);
        const has = labels.some(f => decoder.decode(f.value) === DIRECT_LABEL);
        const groupOutput = [];
        for (const label of group) {
          if (!has && label.number === 2 && label.wire === 2 && decoder.decode(label.value) === SOURCE_LABEL) {
            groupOutput.push(wireField(2, 2, DIRECT_LABEL)); placed = true;
          }
          groupOutput.push(label.raw);
        }
        sortOutput.push(wireField(2, 2, concat(groupOutput)));
      }
      output.push(wireField(2, 2, concat(sortOutput)));
    }
    if (!placed) output.push(wireField(2, 2, concat([wireField(1, 2, 'Local modes'),
      wireField(2, 2, concat([wireField(1, 2, 'Enterprise Models'), wireField(2, 2, DIRECT_LABEL)]))])));
    return { bytes: concat(output), registered: true };
  }
  function statusWire(bytes, carbon = CARBON) {
    const top = parseWire(bytes), statusBytes = fieldValue(top, 1);
    if (!(statusBytes instanceof Uint8Array)) return { bytes, registered: false };
    const status = parseWire(statusBytes), catalogBytes = fieldValue(status, 33);
    if (!(catalogBytes instanceof Uint8Array)) return { bytes, registered: false };
    const result = catalogWire(catalogBytes, carbon);
    if (!result.registered) return { bytes, registered: false };
    const changed = replaceWire(status, new Map([[33, wireField(33, 2, result.bytes)]]));
    return { bytes: replaceWire(top, new Map([[1, wireField(1, 2, changed)]])), registered: true };
  }
  function mapFrames(bytes, transform) {
    const parts = []; let at = 0, changed = false;
    while (at < bytes.length) {
      if (at + 5 > bytes.length) throw Error('Truncated RPC frame');
      const flags = bytes[at], size = new DataView(bytes.buffer, bytes.byteOffset + at + 1, 4).getUint32(0);
      if (at + 5 + size > bytes.length) throw Error('Truncated RPC payload');
      const payload = bytes.slice(at + 5, at + 5 + size);
      const next = flags === 0 ? transform(payload) : payload;
      if (next !== payload) changed = true;
      const header = new Uint8Array(5); header[0] = flags;
      new DataView(header.buffer).setUint32(1, next.length);
      parts.push(header, next); at += 5 + size;
    }
    return changed ? concat(parts) : bytes;
  }
  function mapBody(type, bytes, jsonTransform, wireTransform) {
    const json = /(?:json)(?:;|$)/.test(type);
    const proto = /(?:proto|protobuf)(?:;|$)/.test(type);
    if (!json && !proto) return bytes;
    const transform = payload => {
      if (!json) return wireTransform(payload);
      const data = JSON.parse(decoder.decode(payload)), next = jsonTransform(data);
      return next === data ? payload : encoder.encode(JSON.stringify(next));
    };
    return /grpc|connect\+/.test(type) ? mapFrames(bytes, transform) : transform(bytes);
  }
  function install(root) {
    if (root.__AGProCarbonModes?.version === VERSION) return root.__AGProCarbonModes;
    const config = root.__APP_CONFIG__;
    if (!root.document || root.top !== root.self || (config && (!Object.hasOwn(CARBON_BY_VERSION, config.appVersion)
      || config.productName !== 'antigravity'))
      || !['127.0.0.1', 'localhost'].includes(root.location?.hostname)) return;
    // The Hub's built-in HTTP transport uses the same TLS origin and CSRF rules.
    // Select it before the client captures its transport, preserving all route state.
    const route = new URL(root.location.href);
    route.searchParams.set('useWebSocket', 'false');
    root.history.replaceState(root.history.state, '', route.href);
    const original = root.fetch.bind(root); let registered = false, checkpointLimit;
    root.fetch = async function (input, init) {
      let request, method;
      try {
        request = new Request(input, init);
        const url = new URL(request.url);
        if (url.origin !== root.location.origin || !url.pathname.startsWith(SERVICE)) return original(input, init);
        method = url.pathname.slice(SERVICE.length);
        if (registered && CONFIG_FIELDS[method] && request.method === 'POST') {
          const type = request.headers.get('content-type') || '';
          const raw = new Uint8Array(await request.clone().arrayBuffer());
          const body = mapBody(type, raw, data => requestJson(method, data, checkpointLimit),
            bytes => requestWire(method, bytes, checkpointLimit));
          if (body !== raw) request = new Request(request, { body });
        }
      } catch (_) { return original(input, init); }
      const response = await original(request);
      const carbon = CARBON_BY_VERSION[root.__APP_CONFIG__?.appVersion];
      if (!['GetCascadeModelConfigData', 'GetUserStatus'].includes(method) || !response.ok
        || typeof carbon !== 'number') return response;
      try {
        const type = response.headers.get('content-type') || '', raw = new Uint8Array(await response.clone().arrayBuffer());
        const body = mapBody(type, raw, data => {
          const result = (method === 'GetUserStatus' ? statusJson : catalogJson)(data, carbon);
          registered ||= result.registered; return result.data;
        }, bytes => {
          const result = (method === 'GetUserStatus' ? statusWire : catalogWire)(bytes, carbon);
          registered ||= result.registered; return result.bytes;
        });
        if (body === raw) return response;
        const headers = new Headers(response.headers); headers.delete('content-length');
        return new Response(body, { status: response.status, statusText: response.statusText, headers });
      } catch (_) { return response; }
    };
    return (root.__AGProCarbonModes = { version: VERSION, directId: DIRECT_ID,
      directLabel: DIRECT_LABEL, sourceLabel: SOURCE_LABEL, isReady: () => registered,
      setCheckpointLimit(limit) {
        if (Number.isInteger(limit) && limit > 256000 && limit <= 983040) checkpointLimit = limit;
      } });
  }
  return { VERSION, DIRECT_ID, DIRECT_LABEL, MODEL_INFO, CONFIG_FIELDS, enumValue,
    catalogJson, statusJson, requestJson, requestWire, catalogWire, statusWire, mapFrames, mapBody,
    parseWire, wireField, concat, install };
});
