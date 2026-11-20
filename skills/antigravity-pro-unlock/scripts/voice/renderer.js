(() => {
  if (window.top !== window || location.hostname !== '127.0.0.1' || location.protocol !== 'https:' ||
      !window.agVoicePreview || window.__agVoicePreview) return;
  window.__agVoicePreview = true;
  const url = new URL(location.href);
  url.searchParams.set('useWebSocket', 'false');
  history.replaceState(history.state, '', url);
  const fetchNative = window.fetch.bind(window);
  const service = '/exa.language_server_pb.LanguageServerService/';
  const encoder = new TextEncoder(), decoder = new TextDecoder();
  const mime = 'application/grpc-web+json';
  const prefix = 'preview-audio-';
  const maxBytes = 32000 * 90;
  const sessions = new Map();
  // Keep the shipped composer, recorder, and transcript insertion intact.
  let mode = 'gateway';
  const style = document.createElement('style');
  style.textContent = `
    html[data-ag-dictation-backend="gateway"] [data-agent-composer-root]
    span:has(> [data-testid="voice-live-pill"] :is(button[aria-label="Start Voice mode"], button[aria-label="Start Live Chat"])) {
      display: none !important;
    }
  `;
  document.documentElement.append(style);
  function setMode(value) {
    mode = value === 'native' ? 'native' : 'gateway';
    document.documentElement.dataset.agDictationBackend = mode;
  }
  setMode(window.agVoicePreview.mode());
  window.agVoicePreview.onModeChange(setMode);

  // 2.33.0's shipped recorder assumes streaming results and aborts after 3 s.
  // Match its finalization callbacks only while our own Gateway stream is active.
  const nativeSetTimeout = window.setTimeout;
  const finalizers = [
    /^\(\)=>\{Q\.current=null;if\(L\.current\)\{let \w+=L\.current;L\.current=null;\w+\.stop\(\)\}M\.current\&\&\(M\.current\.abort\(\),M\.current=null\);N\.current=null;w\(!1\);y\(/,
    /^\(\)=>\{P\.current=null;Q\.current===(?:xc|wd)\&\&(?:\(Nb\(\),y\(!1\),Xa\(\)\)|xc\?\.\(\))\}$/,
  ];
  window.setTimeout = function(callback, delay, ...args) {
    if (delay === 3000 && sessions.size && typeof callback === 'function' &&
        finalizers.some(pattern => pattern.test(Function.prototype.toString.call(callback)))) delay = 30000;
    return nativeSetTimeout.call(window, callback, delay, ...args);
  };

  let notice, noticeTimer;
  function showError(detail) {
    notice?.remove();
    clearTimeout(noticeTimer);
    const composer = document.querySelector('[data-agent-composer-root]:focus-within') ||
      document.querySelector('[data-agent-composer-root]');
    if (!composer) return;
    notice = document.createElement('div');
    notice.setAttribute('role', 'status');
    notice.style.cssText = 'font-size:12px;color:var(--muted-foreground);padding:4px 8px';
    notice.textContent = detail;
    composer.append(notice);
    noticeTimer = setTimeout(() => notice?.remove(), 7000);
  }

  function frame(bytes, flag = 0) {
    const out = new Uint8Array(bytes.length + 5);
    out[0] = flag;
    new DataView(out.buffer).setUint32(1, bytes.length);
    out.set(bytes, 5);
    return out;
  }
  const message = data => frame(encoder.encode(JSON.stringify(data)));
  const trailer = (code = 0, detail = '') => frame(encoder.encode(
    'grpc-status: ' + code + '\r\n' + (detail ? 'grpc-message: ' + encodeURIComponent(detail) + '\r\n' : '')), 128);
  const response = body => new Response(body, {headers: {'Content-Type': mime}});
  const ack = () => response(new Blob([message({}), trailer()]));
  const fail = detail => response(new Blob([trailer(13, detail)]));

  function dispose(id) {
    const s = sessions.get(id);
    if (!s) return;
    clearTimeout(s.timer);
    s.signal.removeEventListener('abort', s.abort);
    sessions.delete(id);
    s.chunks.clear();
  }
  function close(id, code, detail) {
    const s = sessions.get(id);
    if (!s) return;
    s.stream.enqueue(trailer(code, detail));
    s.stream.close();
    dispose(id);
  }
  function start(req) {
    if (sessions.size) return fail('Finish the current recording first.');
    if (req.signal.aborted) throw new DOMException('Aborted', 'AbortError');
    notice?.remove();
    const id = prefix + crypto.randomUUID();
    return response(new ReadableStream({
      start(controller) {
        const abort = () => {
          dispose(id);
          controller.error(new DOMException('Aborted', 'AbortError'));
        };
        const timer = setTimeout(() => close(id, 13, 'Recording timed out.'), 150000);
        sessions.set(id, {stream: controller, chunks: new Map(), size: 0, timer, abort, signal:req.signal});
        req.signal.addEventListener('abort', abort, {once:true});
        controller.enqueue(message({ready: {sessionId: id}}));
      },
      cancel() { dispose(id); },
    }));
  }
  async function finish(id, lastSequence) {
    const s = sessions.get(id);
    if (s.ending) return;
    s.ending = true;
    try {
      const order = [...s.chunks.keys()].sort((a,b) => a-b);
      if (order.some((n,i) => n !== i) || (lastSequence != null && lastSequence !== order.length-1))
        throw new Error('Incomplete audio.');
      if (s.size) {
        const pcm = new Uint8Array(s.size);
        let at = 0;
        for (const n of order) {const c = s.chunks.get(n); pcm.set(c,at); at += c.length;}
        const result = await window.agVoicePreview.transcribe(pcm.buffer);
        if (!sessions.has(id)) return;
        if (result.error) {
          showError(result.error);
          close(id, 13, result.error);
          return;
        }
        if (result.text) s.stream.enqueue(message({transcription: {text: result.text, isFinal: true}}));
        else showError('No speech detected.');
      }
      s.stream.enqueue(message({complete: {}}));
      close(id, 0);
    } catch (err) {
      const detail = err.message === 'Incomplete audio.' ? 'The recording was incomplete. Please try again.' : 'Gateway dictation failed. Please try again.';
      showError(detail);
      close(id, 13, detail);
    }
  }

  window.fetch = async (input, init) => {
    const u = new URL(input instanceof Request ? input.url : String(input), location.href);
    if (u.origin !== location.origin || !u.pathname.startsWith(service)) return fetchNative(input,init);
    const method = u.pathname.slice(service.length);
    if (!['StreamAudioTranscription','SendAudioChunk','EndAudioSession'].includes(method)) return fetchNative(input,init);
    if (method === 'StreamAudioTranscription' && mode === 'native') return fetchNative(input,init);
    if (method !== 'StreamAudioTranscription' && !sessions.size && mode === 'native') return fetchNative(input,init);
    const req = new Request(input,init);
    if (!req.headers.get('content-type')?.startsWith(mime)) return fail('The preview expects desktop gRPC-Web JSON.');
    let data;
    try {
      const b = new Uint8Array(await req.clone().arrayBuffer());
      if (b.length < 5 || b[0] !== 0 || new DataView(b.buffer).getUint32(1) !== b.length-5) throw Error();
      data = JSON.parse(decoder.decode(b.subarray(5)));
    } catch {return fail('Invalid dictation request.');}
    if (method === 'StreamAudioTranscription')
      return data.mimeType === 'audio/pcm;rate=16000' ? start(req) : fail('Expected 16 kHz PCM.');
    const id = data.sessionId;
    if (typeof id !== 'string' || !id.startsWith(prefix)) return fetchNative(input,init);
    const s = sessions.get(id);
    if (!s) return fail('Recording session has ended.');
    if (method === 'EndAudioSession') {void finish(id,data.lastSequenceNumber); return ack();}
    const n = Number(data.sequenceNumber ?? 0);
    if (!Number.isSafeInteger(n) || n < 0 || s.ending) return fail('Invalid audio sequence.');
    if (s.chunks.has(n)) return ack();
    try {
      if (typeof data.data !== 'string' || data.data.length > 512000 || s.chunks.size >= 15000) throw Error();
      const c = Uint8Array.from(atob(data.data), v => v.charCodeAt(0));
      if (s.size+c.length > maxBytes) throw Error();
      s.chunks.set(n,c);
      s.size += c.length;
    } catch {
      close(id,13,'Recording limit exceeded.');
      return fail('Recording limit exceeded.');
    }
    return ack();
  };
})();
