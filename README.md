# EVA — Proyecto combinado

```
├── backend/    # EvaBot: Django (async) + Gemini/Groq. Sigue teniendo su propia interfaz en http://localhost:8000
└── frontend/   # EVA: React 19 + Vite + Tailwind
    └── EVA/    # app de Vite (package.json, src/, vite.config.js)
```

El frontend de React ya está **conectado** al backend:

| Función | En React | Endpoint de Django |
|---|---|---|
| Curso del login → materia de Eva | `App.jsx` (`ensureSetup`) | `/api/setup/` |
| Chat con respuesta en streaming (efecto máquina de escribir) | `App.jsx` + `api.js` (`streamChat`) | `/api/chat/` (SSE) |
| Adjuntar PDF, Word, Excel, TXT o foto | `App.jsx` (clip) | `/api/upload/` |
| Nuevo chat (menú ⋮) | `App.jsx` (`newChat`) | `/api/reset/` |
| Dictado por voz | `live/useDictation.js` | `/api/transcribe/` |
| "Escuchar" respuesta | `live/listen.js` + `live/ListenButton.jsx` | `/api/tts/` |
| **Modo live (EvaExplica)**, portado de vanilla a React | `live/LiveMode.jsx` | `/api/live/token/`, `/api/live/save/` |
| Cookie CSRF para React | `api.js` (`initSession`) | `/api/csrf/` (nuevo) |

Las animaciones del backend (modo live, isla dinámica, Eva animada, puntos de "escribiendo", botón Escuchar) están
copiadas tal cual en `frontend/EVA/src/live/eva-live.css`, y Tailwind está instalado en el frontend
(`tailwind.config.js`, `postcss.config.js`, `src/tailwind.css`). El *preflight* de Tailwind está apagado para no
alterar los estilos que ya tenía la app (`App.css`, `index.css`).

## Cómo correrlo (dos terminales)

### 1. Backend (Django) — puerto 8000

```bash
cd backend
python -m venv venv
venv\Scripts\activate          # Windows  (Mac/Linux: source venv/bin/activate)
pip install -r requirements.txt
# crea backend/.env con SECRET_KEY, DEBUG=True y GEMINI_API_KEY (ver backend/README.md)
python manage.py migrate
uvicorn config.asgi:application --reload
```

> Usa `DEBUG=True` en desarrollo: con `DEBUG=False` la cookie de sesión es `Secure` y no viaja por `http://localhost`.

### 2. Frontend (React + Vite) — puerto 5173

```bash
cd frontend/EVA
npm install
npm run dev
```

Abre **http://localhost:5173**. Vite reenvía todo lo que empieza por `/api` a `http://127.0.0.1:8000`
(ver `vite.config.js`), así el navegador ve un solo origen y la sesión y el CSRF funcionan sin configurar CORS.

## Seguridad y rendimiento

Protecciones del backend:

- **Modo live sellado**: la configuración de la sesión (modelo, instrucciones y reglas de Eva) va dentro del token
  de un solo uso (`bidiGenerateContentSetup`). Si alguien copia el token, no puede usar tu clave de Gemini con otras
  instrucciones. Para diagnosticar existe `LIVE_LOCK_SETUP=False` en `.env`, pero en uso normal debe quedarse en `True`.
- **Límite de peticiones por IP** (`chat/ratelimit.py`): chat 30/min, voz 60/min, dictado y subidas 15/min, live 6/min.
  Pasado el límite responde 429 y el frontend muestra el aviso. Detrás de un proxy de confianza, activa
  `RATELIMIT_TRUST_X_FORWARDED_FOR=True`. Con varios procesos, usa Redis en `CACHES`.
- **Archivos**: se rechazan los de más de 8 MB antes de leerlos. Se bloquean los Word/Excel tipo "zip bomb"
  (más de 80 MB al descomprimirse). Los PDF se leen como máximo hasta la página 300.
- Máximo 400 mensajes por conversación.
- Las conversaciones de más de 12 h también se borran cuando entra la app de React.
- Cookies CSRF y de sesión `Secure` en producción. Cabeceras `Referrer-Policy` y `COOP`. HSTS opcional con `SECURE_HSTS_SECONDS`.

Rendimiento del frontend:

- Avatares en WebP de 320 px (`src/assets/avatars/`): unos 114 KB en vez de unos 3 MB. Los originales siguen en `src/assets/`.
- El carrusel (Swiper) se carga solo al abrir esa pantalla. El JS inicial bajó de 348 KB a unos 262 KB.
- Las burbujas del chat están memorizadas: mientras Eva escribe, solo se vuelve a pintar su burbuja.
- Las imágenes de Eva del modo live se descargan solo al abrirlo.
- "Nuevo chat" cancela la respuesta en curso y libera la memoria de las fotos enviadas.

**Pendiente para producción:** pon un límite de tamaño de petición en el proxy (p. ej. `client_max_body_size 12m;`
en nginx). Con uvicorn, Django recibe el cuerpo completo antes de que corra cualquier vista. Además, la pantalla de
"Usuario / Código" del frontend es solo visual: no hay login real, así que cualquiera con la URL puede usar a Eva.

## Notas

- El modo live y el dictado necesitan micrófono y un contexto seguro (`localhost` o HTTPS).
- `swiper` se añadió a `frontend/EVA/package.json`: antes solo estaba en `frontend/package.json` y `npm run build`
  fallaba porque no encontraba React desde ahí.
- En producción hay que servir el `dist/` de Vite y el backend bajo el mismo dominio (o un proxy que mande `/api`
  a Django), igual que hace Vite en desarrollo.
