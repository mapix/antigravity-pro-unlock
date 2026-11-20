'use strict';
const {readFile} = require('node:fs/promises');
const fs = require('node:fs');
const {types} = require('node:util');
const LIMIT = 32000 * 90;
const ROUTE = '/vertex_ai/v1/projects/configured-project/locations/global/publishers/google/models/gemini-3.5-transcribe:generateContent';

class VoiceError extends Error {
  constructor(code, message) { super(message); this.code = code; }
}

function wav(pcm) {
  if (!types.isArrayBuffer(pcm) || !pcm.byteLength || pcm.byteLength > LIMIT || pcm.byteLength % 2)
    throw new VoiceError('audio-format', 'The recording could not be read. Please try again.');
  const n = pcm.byteLength, h = Buffer.alloc(44);
  h.write('RIFF'); h.writeUInt32LE(n + 36, 4); h.write('WAVEfmt ', 8);
  h.writeUInt32LE(16, 16); h.writeUInt16LE(1, 20); h.writeUInt16LE(1, 22);
  h.writeUInt32LE(16000, 24); h.writeUInt32LE(32000, 28);
  h.writeUInt16LE(2, 32); h.writeUInt16LE(16, 34);
  h.write('data', 36); h.writeUInt32LE(n, 40);
  return Buffer.concat([h, Buffer.from(pcm)]);
}

async function transcribe(configPath, pcm, fetchImpl = fetch) {
  const audio = wav(pcm);
  let gateway, base;
  try {
    ({gateway} = JSON.parse(await readFile(configPath, 'utf8')));
    base = new URL(gateway?.url);
  } catch {
    throw new VoiceError('gateway-config', 'The Gateway dictation configuration could not be read.');
  }
  if (!gateway.enabled || base.protocol !== 'https:' || base.username || base.password ||
      base.search || base.hash || typeof gateway.apiKey !== 'string' || !gateway.apiKey)
    throw new VoiceError('gateway-config', 'An enabled HTTPS Gateway is required.');
  let res, data;
  try {
    res = await fetchImpl(base.href.replace(/\/$/, '') + ROUTE, {
      method: 'POST', redirect: 'error', signal: AbortSignal.timeout(25000),
      headers: {'Authorization': 'Bearer ' + gateway.apiKey, 'Content-Type': 'application/json'},
      body: JSON.stringify({
        contents: [{role: 'user', parts: [{inlineData: {mimeType: 'audio/wav', data: audio.toString('base64')}}]}],
        generationConfig: {audioTranscriptionConfig: {languageCodes: ['cmn-Hans-CN', 'en-US']}},
      }),
    });
    if (!res.ok) throw new VoiceError('http-' + res.status, 'Gateway transcription returned HTTP ' + res.status + '.');
    data = await res.json();
  } catch (err) {
    if (err instanceof VoiceError) throw err;
    if (err.name === 'TimeoutError') throw new VoiceError('gateway-timeout', 'Gateway dictation timed out. Please try again.');
    if (err instanceof SyntaxError) throw new VoiceError('gateway-response', 'Gateway returned an unreadable dictation response.');
    const reason = /^(?:E[A-Z0-9_]+|UND_ERR_[A-Z_]+|CERT_[A-Z_]+|UNABLE_TO_[A-Z_]+)$/.test(err.cause?.code ?? '') ? err.cause.code : 'other';
    throw new VoiceError('gateway-network-' + reason, 'Could not connect to the Gateway for dictation.');
  }
  const parts = data?.candidates?.[0]?.content?.parts ?? [];
  if (!Array.isArray(parts) || parts.some(p => !p || typeof p !== 'object'))
    throw new VoiceError('gateway-response', 'Gateway returned an unreadable dictation response.');
  return parts.filter(p => !p.thought).map(p => p.audioTranscription?.text ?? p.text ?? '').join('').trim();
}

function register({ipcMain, configPath, modePath, getPort}) {
  const isPreviewFrame = frame => {
    const port = getPort();
    if (!port || !frame || frame.parent) return false;
    try {
      return new URL(frame.url).origin === 'https://127.0.0.1:' + port;
    } catch {
      return false;
    }
  };
  let mode = 'gateway', busy = false;
  try {
    if (fs.readFileSync(modePath, 'utf8').trim() === 'native') mode = 'native';
  } catch (err) {
    if (err.code !== 'ENOENT') console.error('Could not read the preview dictation preference.');
  }
  ipcMain.on('ag-voice-preview:mode', event => {
    event.returnValue = isPreviewFrame(event.senderFrame) ? mode : null;
  });
  ipcMain.handle('ag-voice-preview:transcribe', async (event, pcm) => {
    if (!isPreviewFrame(event.senderFrame)) throw new Error('Dictation requires the local preview window.');
    if (busy) throw new Error('A transcription is already running.');
    busy = true;
    const started = Date.now();
    try {
      const text = await transcribe(configPath, pcm);
      console.info('Gateway dictation:', text ? 'accepted' : 'empty', Date.now() - started, 'ms');
      return {text};
    } catch (err) {
      console.warn('Gateway dictation:', err instanceof VoiceError ? err.code : 'internal-error', Date.now() - started, 'ms');
      return {error: err instanceof VoiceError ? err.message : 'Gateway dictation failed. Please try again.'};
    } finally {
      busy = false;
    }
  });
  return function installMenu({Menu, MenuItem, BrowserWindow, dialog}) {
    const menu = Menu.getApplicationMenu();
    const appMenu = menu?.items[0]?.submenu;
    if (!appMenu || menu.getMenuItemById('ag-voice-preview-mode')) return;
    const items = {};
    for (const [value, label] of [['gateway', 'Gateway'], ['native', 'Antigravity native']]) {
      items[value] = new MenuItem({label, type: 'radio', checked: mode === value, click() {
        try {
          fs.writeFileSync(`${modePath}.tmp`, value + '\n', {mode: 0o600});
          fs.renameSync(`${modePath}.tmp`, modePath);
        } catch {
          items[mode].checked = true;
          dialog.showErrorBox('Dictation Backend', 'Could not save the dictation preference.');
          return;
        }
        mode = value;
        for (const win of BrowserWindow.getAllWindows()) {
          const frame = win.webContents.mainFrame;
          if (isPreviewFrame(frame)) frame.send('ag-voice-preview:mode-changed', mode);
        }
      }});
    }
    const submenu = new Menu();
    submenu.append(items.gateway);
    submenu.append(items.native);
    appMenu.insert(2, new MenuItem({id: 'ag-voice-preview-mode', label: 'Dictation Backend', submenu}));
    Menu.setApplicationMenu(menu);
  };

}
module.exports = {wav, transcribe, register};
