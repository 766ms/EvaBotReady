# Eva · chatbot educativo (Django async + Gemini + SSE)

Tutora de estudio con respuestas en streaming (efecto máquina de escribir), adjuntos de estudio,
dictado por voz y filtros de seguridad. Usa Google Gemini en su **plan gratuito**.

## Estructura

```
eva/
├── manage.py
├── requirements.txt
├── .env.example            # copia a .env y completa tus valores
├── config/                 # proyecto Django: settings, urls, asgi, wsgi
└── chat/
    ├── models.py           # Conversation y Message (solo sesión, sin perfiles)
    ├── views.py            # vistas async + SSE
    ├── urls.py
    ├── gemini.py           # cliente Gemini y selección automática del modelo más rápido
    ├── groq_client.py      # respaldo de chat con Groq
    ├── llm.py              # orquesta Gemini + Groq (carrera si Gemini tarda)
    ├── transcription.py    # dictado: Whisper en Groq, con respaldo local
    ├── tts.py              # "Escuchar": texto a voz con Groq (Orpheus)
    ├── live.py             # modo live: token efímero y configuración de la sesión de voz
    ├── guardrails.py       # filtro local de groserías, violencia y autolesiones
    ├── prompts.py          # System Prompt e historial en formato Gemini
    ├── attachments.py      # extracción de texto de PDF, Word, Excel, TXT e imágenes
    ├── tests.py
    └── templates/chat/index.html   # interfaz responsive + adjuntos + dictado + modo live

tailwind.config.js · tailwind.input.css   # para reconstruir chat/static/chat/tailwind.css (ver abajo)
```

## Instalación (Mac/Linux)

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # y pon tu GEMINI_API_KEY (gratis en https://aistudio.google.com/apikey)
python manage.py migrate
uvicorn config.asgi:application --reload
```

En Windows: `python -m venv venv` y `venv\Scripts\activate`.

Abre http://127.0.0.1:8000. Para generar una `SECRET_KEY`:
`python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"`

Ejecuta las pruebas con `python manage.py test chat`.

## Selección automática del modelo de Gemini

`chat/gemini.py` no prueba modelos al arrancar (eso gastaría cuota gratuita). Aprende sobre la marcha:

1. Consulta la lista de modelos Flash con streaming disponibles para tu clave (se guarda 1 hora).
2. Ordena por calidad: Flash antes que Flash-Lite, estables antes que preview, versión más nueva primero.
3. Mide el tiempo hasta el primer token de cada modelo y prioriza los más rápidos.
4. Si un modelo devuelve 429 (cuota), 404, error 5xx o tarda más de `FIRST_TOKEN_TIMEOUT` segundos en empezar, lo deja en espera y usa el siguiente sin que el estudiante lo note.

Si quieres fijar el orden tú, usa `GEMINI_MODELS=gemini-2.5-flash,gemini-2.5-flash-lite` en `.env`.

## Seguridad (tres capas)

1. **Filtro local** (`guardrails.py`): bloquea groserías, insultos, violencia explícita y autolesiones en primera persona antes de llamar al modelo. El mensaje no se guarda ni se envía. Las autolesiones responden con líneas de ayuda; un tema educativo como "causas del suicidio" no se bloquea.
2. **System Prompt**: reglas de tutora, ceñirse a la materia y tema, y no obedecer instrucciones que cambien las reglas (también dentro del documento adjunto).
3. **`safetySettings` de Gemini**: filtro propio de Google sobre las respuestas (acoso, odio, contenido sexual explícito y peligroso).

Líneas de ayuda en Colombia: **106** (orientación psicológica y primeros auxilios emocionales, gratis) y **123** (emergencias).

El filtro local es una lista de palabras: es fácil de evadir con ortografía creativa, por eso las capas 2 y 3 son necesarias. Amplía las listas en `guardrails.py` según tu caso.

## Dictado por voz

- Botón de micrófono en la barra de escritura. Graba en el navegador y transcribe en el servidor
  (Whisper en Groq si hay `GROQ_API_KEY`; si no, Whisper local con `faster-whisper`). Ver `STT_PROVIDER` en `transcription.py`.
- Requiere **HTTPS** o `localhost`.

## Escuchar las respuestas (texto a voz con Groq)

- Cada respuesta de Eva tiene un botón de altavoz al terminar de escribirse. Toca para escucharla; toca otra vez para detenerla.
  El audio se pide a `POST /api/tts/`, que llama a Groq (`GROQ_API_KEY`). El navegador guarda el audio ya pedido, así que volver a escucharlo no gasta cuota.
- La respuesta se parte en trozos de hasta 190 caracteres (Groq admite 200 por petición) y se reproducen en orden; el siguiente trozo se descarga mientras suena el actual.
- Si Groq no responde, el resto se lee con la voz del propio navegador (`speechSynthesis`, en español de Colombia).
- Variables opcionales en `.env`: `GROQ_TTS_MODEL` (por defecto `canopylabs/orpheus-v1-english`) y `GROQ_TTS_VOICE` (por defecto `diana`; también `autumn`, `hannah`, `austin`, `daniel`, `troy`).

**Limitación importante:** el modelo de Groq disponible hoy es solo en inglés. Las respuestas en español se leen con acento inglés. Cambia `GROQ_TTS_MODEL` cuando haya una voz en español.

## Modo live (conversación hablada con Eva)

Botón de ondas en la barra de escritura. El navegador se conecta **directo** a la Live API de Gemini (sin pasar por Django),
así la respuesta llega más rápido.

1. El navegador pide a Django `POST /api/live/token/`.
2. Django usa tu `GEMINI_API_KEY` para pedir a Google un **token de un solo uso** (vale 1 min para abrir la sesión y
   `LIVE_TOKEN_MINUTES` para hablar). Tu clave real nunca llega al navegador.
3. Django devuelve el token, las instrucciones de Eva (incluida la materia, el tema, el texto del archivo adjunto y los últimos
   mensajes del chat de texto, para que siga donde quedó) y las
   expresiones regulares del filtro de `guardrails.py`.
4. El navegador envía el audio del micrófono (PCM 16 kHz) y reproduce la voz de Eva (PCM 24 kHz). La transcripción se ve en el pop-up y, si lo minimizas, también en el chat.

Variables opcionales en `.env`: `GEMINI_LIVE_MODEL` (por defecto `gemini-3.8-live`), `GEMINI_LIVE_VOICE` (por defecto `Aoede`)
y `LIVE_TOKEN_MINUTES` (por defecto 20).

**Pop-up «EvaExplica»:**

- Al empezar la sesión aparece el aviso de bienvenida (Eva es una IA, puede equivocarse y no reemplaza a un tutor).
- **Isla dinámica** encima de los botones: *Conectando…* → *Te escucha…* → *Escuchándote…* (ondas que siguen tu voz) →
  *Pensando…* → *Respondiendo…* (ondas que siguen la voz de Eva). Si silencias el micrófono: *Micrófono en silencio*.
  La detección de voz se hace en el navegador midiendo el nivel del micrófono (`levelLoop` en `index.html`).
- **Botones:** micrófono (silenciar/activar sin cortar la llamada), teclado (pasar al chat), clip (añadir archivo) y Terminar.
- **Minimizar** muestra el chat con su caja de escribir; lo hablado pasa al chat y sigue apareciendo ahí mientras dure la sesión.
- **Animación de Eva** (todo en CSS, sin librerías): al cambiar de pose se funden sin verse transparentes y cada pose entra con un
  pequeño salto o asentamiento; al hablar se mueve con el volumen de su voz; al escucharte se inclina un poco hacia ti y al
  pensar ladea la cabeza. Con "reducir movimiento" activado en el sistema, todo queda quieto.
- **Responsive:** en celular Eva ocupa un tercio de la altura (`clamp` según la pantalla) y el resto es para el texto; en pantallas bajas
  los controles se compactan; con el celular acostado se usa el diseño de dos columnas de PC.
- Las tres poses de Eva (`chat/static/chat/eva/`) comparten el mismo lienzo con los pies centrados, así la muñeca no se corre
  de lado al cambiar de animación. Si cambias las imágenes, mantén ese lienzo (mismo ancho y alto, pies en el centro).

**Filtro en modo live** (misma fuente que el chat: `guardrails.py`):

- Una obscenidad: Eva no responde (se corta el audio de esa respuesta) y el mensaje del estudiante se oculta.
- Tres turnos obscenos seguidos (una frase limpia reinicia la cuenta): Eva cierra la sesión y avisa.
- Violencia explícita o autolesiones: cierra de inmediato. En autolesiones el aviso incluye la Línea 106 y el 123.
- Limitaciones: el filtro corre en el navegador, así que un usuario técnico podría saltárselo; las reglas del System Prompt
  siguen activas como segunda barrera. En live no se analizan imágenes adjuntas (sí el texto de PDF, Word, Excel y TXT).
  Lo hablado se guarda en el historial (y Eva lo recuerda al escribir) cuando pulsas el teclado o terminas una sesión
  que minimizaste; si terminas sin haberla minimizado, la transcripción se descarta.
- El plan gratuito de Gemini puede tener límites de uso más bajos y usa el contenido para mejorar los productos de Google.

## Tailwind

`tailwind.css` es un archivo compilado. Si agregas clases nuevas en el HTML, reconstrúyelo:

```bash
npx tailwindcss@3.4.17 -c tailwind.config.js -i tailwind.input.css -o chat/static/chat/tailwind.css --minify
```

## Privacidad

- Sin cuentas ni perfiles. La conversación vive en la sesión y se borra al recargar la página o con "Nuevo chat".
- Eva recuerda solo los últimos 12 mensajes de la sesión.
- Las conversaciones de más de 12 horas se eliminan. Para limpiar sesiones viejas: `python manage.py clearsessions`.
