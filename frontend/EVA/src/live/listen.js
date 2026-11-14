// "Escuchar" junto a cada respuesta de Eva: texto a voz con Groq (/api/tts/); si no responde, voz del navegador.
// Portado de la plantilla de Django (backend/chat/templates/chat/index.html).
import { post, urls } from '../api';

const TTS_MAX = 190; // Groq (Orpheus) admite hasta 200 caracteres por petición
export const LISTEN_LABEL = { idle: 'Escuchar respuesta', loading: 'Preparando audio…', playing: 'Detener audio' };
const ttsCache = new Map(); // trozo de texto -> URL del audio: volver a escucharlo no vuelve a gastar Groq
let speech = null; // reproducción en curso: {id, cancelled, audio, utter}

// Estado compartido con React: solo un botón suena a la vez
let snapshot = { id: null, state: 'idle' };
const listeners = new Set();
export const subscribe = (l) => { listeners.add(l); return () => listeners.delete(l); };
export const getSnapshot = () => snapshot;
function setListen(id, state) { snapshot = { id, state }; listeners.forEach((l) => l()); }

// Parte la respuesta en trozos de hasta TTS_MAX caracteres, respetando frases y, si hace falta, espacios
function ttsChunks(text) {
  const sentences = (text.replace(/\s+/g, ' ').trim().match(/[^.!?…]+[.!?…]*\s*/g) || []).map((s) => s.trim()).filter(Boolean);
  const out = [];
  let cur = '';
  for (let s of sentences) {
    while (s.length > TTS_MAX) {
      let cut = s.lastIndexOf(' ', TTS_MAX);
      if (cut < 1) cut = TTS_MAX;
      if (cur) { out.push(cur); cur = ''; }
      out.push(s.slice(0, cut).trim());
      s = s.slice(cut).trim();
    }
    if (cur && cur.length + 1 + s.length > TTS_MAX) { out.push(cur); cur = s; }
    else cur = cur ? cur + ' ' + s : s;
  }
  if (cur) out.push(cur);
  return out;
}

function ttsFetch(t) {
  if (!ttsCache.has(t)) {
    const p = post(urls.speak, { json: { text: t } })
      .then(async (r) => { if (!r.ok) throw new Error('tts'); return URL.createObjectURL(await r.blob()); });
    p.catch(() => ttsCache.delete(t));
    ttsCache.set(t, p);
    if (ttsCache.size > 40) { // límite de memoria: se olvida el audio más antiguo
      const [oldKey, oldVal] = ttsCache.entries().next().value;
      ttsCache.delete(oldKey);
      oldVal.then((u) => URL.revokeObjectURL(u), () => {});
    }
  }
  return ttsCache.get(t);
}

export function stopSpeech() {
  const s = speech;
  if (!s) return;
  speech = null;
  s.cancelled = true;
  s.audio?.pause();
  if (s.utter) speechSynthesis.cancel();
  setListen(s.id, 'idle');
}

function finishListen(s) { if (speech === s) speech = null; setListen(s.id, 'idle'); }

function playUrl(s, url) { // se resuelve al terminar (o al pausar desde "Detener")
  return new Promise((resolve, reject) => {
    const a = (s.audio = new Audio(url));
    a.onended = a.onpause = resolve;
    a.onerror = () => reject(new Error('audio'));
    a.play().catch(reject);
  });
}

function speakWithBrowser(s, text, say) {
  if (!('speechSynthesis' in window)) { finishListen(s); return say?.('No pude leer la respuesta en este momento.'); }
  const u = (s.utter = new SpeechSynthesisUtterance(text));
  u.lang = 'es-CO';
  u.onend = u.onerror = () => finishListen(s);
  setListen(s.id, 'playing');
  speechSynthesis.speak(u);
}

export async function listen(id, text, say) {
  if (speech?.id === id) return stopSpeech(); // segundo toque: detener
  stopSpeech();
  const chunks = ttsChunks(text);
  if (!chunks.length) return;
  const s = (speech = { id, cancelled: false, audio: null, utter: null });
  setListen(id, 'loading');
  let i = 0;
  let pending = ttsFetch(chunks[0]);
  pending.catch(() => {});
  try {
    for (; i < chunks.length; i++) {
      const url = await pending;
      if (s.cancelled) return;
      if (i + 1 < chunks.length) { pending = ttsFetch(chunks[i + 1]); pending.catch(() => {}); } // el siguiente trozo se baja mientras suena este
      setListen(id, 'playing');
      await playUrl(s, url);
      if (s.cancelled) return;
    }
    finishListen(s);
  } catch {
    if (s.cancelled) return;
    speakWithBrowser(s, chunks.slice(i).join(' '), say); // Groq no respondió: el resto se lee con la voz del navegador
  }
}
