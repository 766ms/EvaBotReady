// Cliente del backend de Django (EvaBot).
// En desarrollo Vite reenvía /api al puerto 8000 (ver vite.config.js), así que todo es del mismo origen:
// la cookie de sesión (la conversación) y la cookie csrftoken viajan solas.

export const urls = {
  csrf: '/api/csrf/',
  setup: '/api/setup/',
  upload: '/api/upload/',
  chat: '/api/chat/',
  reset: '/api/reset/',
  transcribe: '/api/transcribe/',
  speak: '/api/tts/',
  liveToken: '/api/live/token/',
  liveSave: '/api/live/save/',
};

function csrfToken() {
  const row = document.cookie.split('; ').find((c) => c.startsWith('csrftoken='));
  return row ? decodeURIComponent(row.slice('csrftoken='.length)) : '';
}

// Pide la cookie CSRF una sola vez (y empieza un chat nuevo en el servidor, como recargar la plantilla de Django)
let ready = null;
export function initSession() {
  ready ??= fetch(urls.csrf, { credentials: 'same-origin' }).catch(() => {});
  return ready;
}

// POST con el token CSRF. `json` se envía como JSON; `body` tal cual (FormData, Blob…)
export async function post(url, { json, body, headers = {}, keepalive = false, signal } = {}) {
  await initSession();
  const h = { 'X-CSRFToken': csrfToken(), ...headers };
  if (json !== undefined) h['Content-Type'] = 'application/json';
  return fetch(url, {
    method: 'POST',
    credentials: 'same-origin',
    keepalive,
    signal,
    headers: h,
    body: json !== undefined ? JSON.stringify(json) : body,
  });
}

// POST que devuelve el JSON o lanza Error con el mensaje del servidor
export async function postJson(url, opts, fallbackError = 'No pude conectar con Eva.') {
  const res = await post(url, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || fallbackError);
  return data;
}

export function uploadFile(file) {
  const fd = new FormData();
  fd.append('file', file);
  return postJson(urls.upload, { body: fd }, 'No pude subir el archivo.');
}

// /api/chat/ responde por SSE: "data: {"t": "..."}\n\n" … "data: [DONE]\n\n"
export async function streamChat(message, onText, signal) {
  const res = await post(urls.chat, { json: { message }, signal });
  if (!res.ok || !res.body) {
    // 400 (conversación muy larga), 429 (demasiadas peticiones)…: se muestra el mensaje del servidor
    const data = await res.json().catch(() => ({}));
    const err = new Error('chat');
    err.userMessage = data.error;
    throw err;
  }
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let acc = '';
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    acc += dec.decode(value, { stream: true });
    const parts = acc.split('\n\n');
    acc = parts.pop();
    for (const p of parts) {
      if (!p.startsWith('data: ') || p === 'data: [DONE]') continue;
      const j = JSON.parse(p.slice(6));
      const t = j.t ?? j.error;
      if (t) onText(t);
    }
  }
}

export const MAX_FILE_BYTES = 8 * 1024 * 1024;
export const FILE_ACCEPT = '.pdf,.docx,.xlsx,.pptx,.txt,.png,.jpg,.jpeg'; // lo que sabe leer backend/chat/attachments.py
export const isImageFile = (f) => f.type.startsWith('image/') || /\.(png|jpe?g)$/i.test(f.name);
