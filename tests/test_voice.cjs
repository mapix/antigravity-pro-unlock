'use strict';
const assert = require('node:assert/strict');
const {mkdtemp, readFile, rm, writeFile} = require('node:fs/promises');
const {tmpdir} = require('node:os');
const {join} = require('node:path');
const {test} = require('node:test');
const {runInNewContext} = require('node:vm');
const voice = join(__dirname, '../skills/antigravity-pro-unlock/scripts/voice');
const {register, transcribe} = require(join(voice, 'gateway.cjs'));

async function config(t, url = 'https://gateway.example.invalid') {
  const dir = await mkdtemp(join(tmpdir(), 'dictation-test-'));
  t.after(() => rm(dir, {recursive: true, force: true}));
  const path = join(dir, 'config.json');
  await writeFile(path, JSON.stringify({gateway: {enabled: true, url, apiKey: 'fixture-key'}}));
  return path;
}

const pcm = Uint8Array.of(1, 2, 3, 4);

test('Gateway accepts WAV with the requested model and returns visible text only', async t => {
  const path = await config(t);
  const result = await transcribe(path, pcm.buffer, async (url, req) => {
    assert.equal(new URL(url).hostname, 'gateway.example.invalid');
    assert.match(url, /\/models\/gemini-3\.5-transcribe:generateContent$/);
    assert.equal(req.redirect, 'error');
    assert.equal(req.headers.Authorization, 'Bearer fixture-key');
    const {contents, generationConfig} = JSON.parse(req.body);
    assert.deepEqual(generationConfig.audioTranscriptionConfig.languageCodes, ['cmn-Hans-CN', 'en-US']);
    const {mimeType, data} = contents[0].parts[0].inlineData;
    assert.equal(mimeType, 'audio/wav');
    const wav = Buffer.from(data, 'base64');
    assert.equal(wav.toString('ascii', 0, 4), 'RIFF');
    assert.equal(wav.readUInt32LE(24), 16000);
    assert.equal(wav.readUInt32LE(40), pcm.length);
    assert.deepEqual(wav.subarray(44), Buffer.from(pcm));
    return Response.json({candidates: [{content: {parts: [
      {thought: true, text: 'internal'}, {audioTranscription: {text: '  dictated text  '}},
    ]}}]});
  });
  assert.equal(result, 'dictated text');
});

test('Gateway refuses an insecure address and does not expose an upstream error body', async t => {
  const insecure = await config(t, 'http://gateway.example.invalid');
  const secure = await config(t);
  await assert.rejects(transcribe(insecure, pcm.buffer, () => assert.fail('network call')), {code: 'gateway-config'});
  await assert.rejects(transcribe(secure, pcm.buffer, async () => new Response('private upstream detail', {status: 403})),
    {code: 'http-403', message: 'Gateway transcription returned HTTP 403.'});
});

test('IPC accepts the top preview frame only and tolerates invalid frame metadata', async t => {
  const path = await config(t);
  const handlers = new Map();
  const ipcMain = {on: (key, fn) => handlers.set(key, fn), handle: (key, fn) => handlers.set(key, fn)};
  register({ipcMain, configPath: path, modePath: join(path, '../mode'), getPort: () => 12345});
  const voiceMode = handlers.get('ag-voice-preview:mode');
  const invoke = handlers.get('ag-voice-preview:transcribe');
  const url = 'https://127.0.0.1:12345/';
  for (const senderFrame of [null, {url: undefined}, {url, parent: {}}, {url: 'https://127.0.0.1:12346/'}]) {
    const event = {senderFrame};
    voiceMode(event);
    assert.equal(event.returnValue, null);
    await assert.rejects(invoke(event, pcm.buffer), /requires the local preview window/);
  }
  const event = {senderFrame: {url, parent: null}};
  voiceMode(event);
  assert.equal(event.returnValue, 'gateway');
});

test('Gateway recorder extends only its finalizer and returns a delayed final transcript', async () => {
  const source = await readFile(join(voice, 'renderer.js'), 'utf8');
  const location = new URL('https://127.0.0.1:12345/');
  const delays = [];
  let finish;
  const bridge = {mode: () => 'gateway', onModeChange() {}, transcribe(audio) {
    assert.deepEqual(new Uint8Array(audio), pcm);
    return new Promise(resolve => { finish = resolve; });
  }};
  const sandbox = {
    URL, Blob, Request, Response, ReadableStream, TextEncoder, TextDecoder, Uint8Array, DOMException, atob,
    crypto: {randomUUID: () => 'test-id'},
    location, history: {replaceState() {}}, agVoicePreview: bridge,
    document: {documentElement: {dataset: {}, append() {}}, createElement: () => ({})},
    fetch: () => assert.fail('unexpected fallback'),
    setTimeout: (_cb, delay) => delays.push(delay), clearTimeout() {},
  };
  sandbox.window = sandbox.top = sandbox;
  runInNewContext(source, sandbox);
  const request = (method, data) => {
    const body = Buffer.from(JSON.stringify(data)), packet = Buffer.alloc(5 + body.length);
    packet.writeUInt32BE(body.length, 1);
    body.copy(packet, 5);
    return sandbox.fetch(location.origin + '/exa.language_server_pb.LanguageServerService/' + method, {
      method: 'POST', headers: {'content-type': 'application/grpc-web+json'}, body: packet,
    });
  };
  const stream = await request('StreamAudioTranscription', {mimeType: 'audio/pcm;rate=16000'});
  const pending = stream.arrayBuffer();
  const sessionId = 'preview-audio-test-id';
  await request('SendAudioChunk', {sessionId, sequenceNumber: 0, data: Buffer.from(pcm).toString('base64')});
  await request('EndAudioSession', {sessionId, lastSequenceNumber: 0});
  const finalizer = runInNewContext('()=>{P.current=null;Q.current===xc&&xc?.()}', sandbox);
  sandbox.setTimeout(finalizer, 3000);
  sandbox.setTimeout(() => {}, 3000);
  assert.deepEqual(delays.slice(-2), [30000, 3000]);
  finish({text: 'delayed transcript'});
  const frames = Buffer.from(await pending);
  assert.match(frames.toString(), /"transcription":\{"text":"delayed transcript","isFinal":true\}/);
  assert.match(frames.toString(), /grpc-status: 0/);
  sandbox.setTimeout(finalizer, 3000);
  assert.equal(delays.at(-1), 3000);
});
