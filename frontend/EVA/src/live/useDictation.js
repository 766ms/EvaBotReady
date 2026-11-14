// Dictado: graba en el navegador y transcribe en el servidor (Whisper, /api/transcribe/).
// Portado de la plantilla de Django (backend/chat/templates/chat/index.html).
import { useLayoutEffect, useRef, useState } from 'react';
import { postJson, urls } from '../api';

const MAX_SECONDS = 60;

export function useDictation({ onText, say }) {
  const [state, setState] = useState('idle'); // "idle" | "rec" | "busy"
  const r = useRef({ recorder: null, stream: null, chunks: [], timer: null, discard: false });
  const cb = useRef({ onText, say });
  useLayoutEffect(() => { cb.current = { onText, say }; });
  const supported = typeof window !== 'undefined' && !!window.MediaRecorder;

  function stop() {
    clearTimeout(r.current.timer);
    const rec = r.current.recorder;
    if (rec && rec.state !== 'inactive') rec.stop();
  }

  // Corta la grabación sin transcribir (al enviar el mensaje o abrir el modo live)
  function cancel() {
    if (r.current.recorder?.state === 'recording') { r.current.discard = true; stop(); }
  }

  async function finish() {
    const R = r.current;
    R.stream?.getTracks().forEach((t) => t.stop());
    if (R.discard) return setState('idle');
    const blob = new Blob(R.chunks, { type: R.recorder.mimeType || 'audio/webm' });
    R.chunks = [];
    if (blob.size < 2000) { setState('idle'); return cb.current.say('No alcancé a grabar nada. Intenta de nuevo.'); }
    setState('busy');
    try {
      const j = await postJson(urls.transcribe, { body: blob, headers: { 'Content-Type': blob.type } }, 'No pude transcribir el audio.');
      if (j.text) { cb.current.onText(j.text); cb.current.say(''); }
      else cb.current.say('No escuché nada. Intenta de nuevo.');
    } catch (e) {
      cb.current.say(e.message);
    } finally {
      setState('idle');
    }
  }

  async function start() {
    const R = r.current;
    cb.current.say('');
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      return cb.current.say('Para dictar, abre Eva con HTTPS o desde localhost.');
    }
    try {
      R.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      return cb.current.say(e.name === 'NotAllowedError' ? 'Permite el uso del micrófono en tu navegador.' : 'No encontré un micrófono disponible.');
    }
    R.chunks = [];
    R.discard = false;
    R.recorder = new MediaRecorder(R.stream);
    R.recorder.ondataavailable = (e) => { if (e.data.size) R.chunks.push(e.data); };
    R.recorder.onstop = finish;
    R.recorder.start();
    setState('rec');
    R.timer = setTimeout(stop, MAX_SECONDS * 1000);
  }

  const toggle = () => (r.current.recorder?.state === 'recording' ? stop() : start());

  return { supported, state, toggle, cancel };
}
