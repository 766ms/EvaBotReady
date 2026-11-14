import { lazy, Suspense, useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import './App.css';
import './live/eva-live.css';
import { initSession, postJson, post, streamChat, uploadFile, urls, MAX_FILE_BYTES, FILE_ACCEPT, isImageFile } from './api';
import LiveMode from './live/LiveMode';
import MessageRow from './MessageRow';
import MenuAjustes from './MenuAjustes';
import { stopSpeech } from './live/listen';
import { useDictation } from './live/useDictation';
// Avatares cargados directamente de src/assets/eva-live
import eva from "./assets/eva-live/quieta.webp";
import AVATAR1 from "./assets/eva-live/SEC1-1.png";
import AVATAR2 from "./assets/eva-live/SEC2-1.png";
import AVATAR3 from "./assets/eva-live/SEC3-1.png";
import AVATAR4 from "./assets/eva-live/SEC4-1.png";
import AVATAR5 from "./assets/eva-live/SEC5-1.png";
import AVATAR6 from "./assets/eva-live/SEC6-1.png";
import AVATAR7 from "./assets/eva-live/SEC7-1.png";
import AVATAR8 from "./assets/eva-live/SEC8-1.png";
import AVATAR9 from "./assets/eva-live/SEC9-1.png";
import AVATAR10 from "./assets/eva-live/SEC10-1.png";
import AVATAR11 from "./assets/eva-live/SEC11-1.png";
import AVATAR12 from "./assets/eva-live/SEC12-1.png";
import AVATAR13 from "./assets/eva-live/SECBAS1.png";
import AVATAR14 from "./assets/eva-live/SECCAR1.png";
import AVATAR15 from "./assets/eva-live/SECEVAN1.png";

// El carrusel (Swiper) solo se descarga al llegar a la pantalla de elegir avatar
const AvatarPicker = lazy(() => import('./AvatarPicker'));

const AVATARS = [
  eva,
  AVATAR1, AVATAR2, AVATAR3, AVATAR4,
  AVATAR5, AVATAR6, AVATAR7, AVATAR8,
  AVATAR9, AVATAR10, AVATAR11, AVATAR12,
  AVATAR13, AVATAR14, AVATAR15
];
const AVATAR_KEY = 'eva-avatar-idx'; // se guarda la posición, no la URL: la URL del archivo cambia en cada build

function loadAvatarIndex() {
  try {
    const i = Number(localStorage.getItem(AVATAR_KEY));
    return Number.isInteger(i) && i >= 0 && i < AVATARS.length ? i : 0;
  } catch {
    return 0; // modo privado o almacenamiento bloqueado
  }
}

// Cursos del login: el nombre se manda al backend como "materia" para que Eva se enfoque en ella
const CURSOS = [
  { value: '1', label: 'Base de datos' },
  { value: '2', label: 'Redes de computo escalable' },
  { value: '3', label: 'Practicas formativas' },
  { value: '4', label: 'Gestión de proyectos' },
  { value: '5', label: 'Calculo integral' },
];

let msgSeq = 0;
const newMsg = (type, text, extra = {}) => ({ id: ++msgSeq, type, text, ...extra });
const formatSize = (b) => (b >= 1024 * 1024 ? (b / (1024 * 1024)).toFixed(1) + ' MB' : (b / 1024).toFixed(0) + ' KB');

/* ---------- Helpers de localStorage ---------- */
function lsGet(key, def = '') {
  try { return localStorage.getItem(key) ?? def; } catch { return def; }
}
function lsSet(key, val) {
  try { localStorage.setItem(key, String(val)); } catch { /* modo privado */ }
}
function lsDel(key) {
  try { localStorage.removeItem(key); } catch { /* modo privado */ }
}

const SESSION_KEYS = {
  usuario:  'eva-usuario',
  codigo:   'eva-codigo',
  curso:    'eva-curso',
  loggedIn: 'eva-logged-in',
};

function App() {
  const [isOpen, setIsOpen] = useState(false);
  // Si hay sesión guardada, arranca directo en 'chat-ready'
  const [currentScreen, setCurrentScreen] = useState(() =>
    lsGet(SESSION_KEYS.loggedIn) === '1' ? 'chat-ready' : 'welcome'
  );
  const [message, setMessage] = useState('');
  const [usuario, setUsuario] = useState(() => lsGet(SESSION_KEYS.usuario));
  const [codigo, setCodigo] = useState(() => lsGet(SESSION_KEYS.codigo));
  const [loginError, setLoginError] = useState('');
  const [curso, setCurso] = useState(() => lsGet(SESSION_KEYS.curso));
  const [isExpanded, setIsExpanded] = useState(false);

  // ESTADOS DEL MENÚ DE AJUSTES
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const menuContainerRef = useRef(null);

  // Cierra el menú al hacer clic afuera o pulsar Escape
  useEffect(() => {
    if (!isMenuOpen) return;
    const handleClickOutside = (e) => {
      if (menuContainerRef.current && !menuContainerRef.current.contains(e.target)) {
        setIsMenuOpen(false);
      }
    };
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') setIsMenuOpen(false);
    };
    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isMenuOpen]);

  // Conversación real con el backend (Django + Gemini) - inicia vacía sin mensaje predeterminado
  const [chatHistory, setChatHistory] = useState(() => []);
  const [busy, setBusy] = useState(false);
  const [hint, setHint] = useState('');                 // avisos cortos (errores, "Subiendo archivo…")
  const [selectedFile, setSelectedFile] = useState(null); // {file, url, isImage}
  const [livePopupOpen, setLivePopupOpen] = useState(false);
  const startedRef = useRef(false);   // ya se mandó /api/setup/ (materia del curso)
  const liveRef = useRef(null);
  const messagesRef = useRef(null);
  const stickRef = useRef(true);      // seguir el final solo si ya estabas ahí
  const inputRef = useRef(null);
  const chatFileRef = useRef(null);
  const abortRef = useRef(null);      // cancela la respuesta en curso (Nuevo chat / cerrar la página)
  const typerRef = useRef(null);      // efecto máquina de escribir en curso
  const blobUrlsRef = useRef([]);     // vistas previas de fotos enviadas: se liberan al empezar otro chat

  const [avatarIndex, setAvatarIndex] = useState(loadAvatarIndex);
  const selectedAvatar = AVATARS[avatarIndex];
  const cursoLabel = CURSOS.find((c) => c.value === curso)?.label || '';

  const say = useCallback((msg) => setHint(msg || ''), []);
  const dictation = useDictation({
    say,
    onText: (text) => setMessage((m) => (m.trim() ? m.trimEnd() + ' ' : '') + text),
  });

  // Cookie CSRF + chat nuevo en el servidor al abrir la app; al desmontar se corta la respuesta en curso
  useEffect(() => {
    initSession();
    return () => abortRef.current?.abort();
  }, []);

  // Desplazamiento automático del chat
  useLayoutEffect(() => {
    const el = messagesRef.current;
    if (el && stickRef.current) el.scrollTop = el.scrollHeight;
  }, [chatHistory, currentScreen]);
  const onMessagesScroll = () => {
    const el = messagesRef.current;
    stickRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 160;
  };

  const addChatMessage = (role, text) => {
    const m = newMsg(role, text, { done: true });
    stickRef.current = true;
    setChatHistory((h) => [...h, m]);
    return m.id;
  };
  const updateChatMessage = (id, text) => setChatHistory((h) => h.map((m) => (m.id === id ? { ...m, text } : m)));

  // Le dice al backend la materia (el curso del login). Se hace una vez por chat.
  const ensureSetup = async () => {
    if (startedRef.current) return;
    const fd = new FormData();
    fd.append('subject', cursoLabel);
    fd.append('topic', '');
    await postJson(urls.setup, { body: fd }, 'No pude guardar la configuración.');
    startedRef.current = true;
  };

  const clearSelectedFile = () => {
    setSelectedFile((f) => { if (f?.url) URL.revokeObjectURL(f.url); return null; });
    if (chatFileRef.current) chatFileRef.current.value = '';
  };

  const pickFile = (file) => {
    if (!file) return;
    if (file.size > MAX_FILE_BYTES) { say('El archivo supera el límite de 8 MB.'); return; }
    const isImage = isImageFile(file);
    setSelectedFile((old) => {
      if (old?.url) URL.revokeObjectURL(old.url);
      return { file, isImage, url: isImage ? URL.createObjectURL(file) : null };
    });
    say('');
  };

  const openChat = () => {
    setIsOpen(true);
    // Si ya hay sesión activa, va directo al chat-ready (no repite login ni avatar)
    if (lsGet(SESSION_KEYS.loggedIn) !== '1') {
      setCurrentScreen('welcome');
    }
  };

  const closeChat = () => {
    setIsOpen(false);
    setIsExpanded(false);
    setIsMenuOpen(false);
  };

  const newChat = async () => {
    abortRef.current?.abort();   // deja de recibir la respuesta anterior (el servidor tampoco la guarda)
    typerRef.current?.cancel();  // y deja de escribirla en pantalla
    liveRef.current?.end();
    stopSpeech();
    await post(urls.reset).catch(() => {});
    startedRef.current = false;
    clearSelectedFile();
    say('');
    blobUrlsRef.current.forEach((u) => URL.revokeObjectURL(u));
    blobUrlsRef.current = [];
    setChatHistory([]); // Limpia la conversación sin enviar mensaje predeterminado
  };

  // Usuario: letras, números, punto, guion bajo, guion
  const handleUsernameInput = (e) => {
    const val = e.target.value.replace(/[^a-zA-Z0-9._-]/g, '');
    setUsuario(val);
    setLoginError('');
  };

  const blockInvalidUsername = (e) => {
    if (
      ['Backspace', 'Delete', 'ArrowLeft', 'ArrowRight', 'Tab', 'Enter'].includes(e.key) ||
      e.ctrlKey || e.metaKey
    ) return;
    if (!/^[a-zA-Z0-9._-]$/.test(e.key)) e.preventDefault();
  };

  // Código: solo números
  const handleNumericInput = (setter) => (e) => {
    const val = e.target.value.replace(/\D/g, '');
    setter(val);
    setLoginError('');
  };

  const blockNonNumeric = (e) => {
    if (
      ['Backspace', 'Delete', 'ArrowLeft', 'ArrowRight', 'Tab', 'Enter'].includes(e.key) ||
      e.ctrlKey || e.metaKey
    ) return;
    if (!/^\d$/.test(e.key)) e.preventDefault();
  };

  const handleLoginSubmit = (e) => {
    e?.preventDefault();
    if (!usuario.trim()) {
      setLoginError('Ingresa tu usuario (letras, números, . _ -).');
      return;
    }
    if (!codigo.trim()) {
      setLoginError('Ingresa tu código numérico (solo números).');
      return;
    }
    if (!curso) {
      setLoginError('Selecciona el curso al que perteneces.');
      return;
    }
    setLoginError('');
    // Persistir credenciales antes de ir al selector de avatar
    lsSet(SESSION_KEYS.usuario, usuario.trim());
    lsSet(SESSION_KEYS.codigo, codigo.trim());
    lsSet(SESSION_KEYS.curso, curso);
    setCurrentScreen('avatar-select');
  };

  // Cerrar sesión: borra datos del perfil y vuelve a la bienvenida
  const logout = () => {
    Object.values(SESSION_KEYS).forEach(lsDel);
    setUsuario('');
    setCodigo('');
    setCurso('');
    setCurrentScreen('welcome');
    newChat();
    setIsMenuOpen(false);
  };

  // Efecto máquina de escribir: suaviza los trozos que llegan por streaming
  // requestAnimationFrame se pausa (o se frena) con la pestaña en segundo plano: un temporizador de respaldo
  // sigue escribiendo para no dejar la respuesta a medias ni el botón de enviar bloqueado. Gana el que llegue primero.
  const typer = (id) => {
    let buf = '', ended = false, resolve;
    const done = new Promise((r) => { resolve = r; });
    const next = (fn) => {
      let ran = false;
      const run = () => { if (!ran) { ran = true; fn(); } };
      requestAnimationFrame(run);
      setTimeout(run, 100);
    };
    (function tick() {
      if (buf) {
        const n = Math.max(1, Math.ceil(buf.length / 25));
        const piece = buf.slice(0, n);
        buf = buf.slice(n);
        setChatHistory((h) => h.map((m) => (m.id === id ? { ...m, pending: false, text: m.text + piece } : m)));
      }
      if (ended && !buf) return resolve();
      next(tick);
    })();
    const ty = { push: (t) => { buf += t; }, end: () => { ended = true; }, cancel: () => { buf = ''; ended = true; }, done };
    typerRef.current = ty;
    return ty;
  };

  const handleSendMessage = async (e) => {
    e?.preventDefault();
    const rawText = message.trim();
    const pending = selectedFile;
    if (!rawText && !pending) return;
    if (busy) return;
    stopSpeech();        // al enviar otra pregunta, se calla la respuesta anterior
    dictation.cancel();  // no transcribir si se envía mientras graba
    setBusy(true);
    try {
      try { await ensureSetup(); } catch (err) { say(err.message); return; }

      let attachment = null;
      if (pending) {
        say('Subiendo archivo…');
        try {
          await uploadFile(pending.file);
          const url = pending.isImage ? URL.createObjectURL(pending.file) : null; // solo las fotos necesitan vista previa
          if (url) blobUrlsRef.current.push(url);
          attachment = { name: pending.file.name, isImage: pending.isImage, url };
          clearSelectedFile();
          say('');
        } catch (err) {
          say(err.message || 'Error al procesar el archivo.');
          return;
        }
      }

      const text = rawText || (attachment
        ? (attachment.isImage ? 'Analiza esta foto y explícame de qué se trata.' : 'Analiza este archivo y explícame sus puntos clave.')
        : '');
      setMessage('');
      const botMsg = newMsg('bot', '', { pending: true, done: false });
      stickRef.current = true;
      setChatHistory((h) => [...h, newMsg('user', text, { attachment, done: true }), botMsg]);
      const ty = typer(botMsg.id);
      const ctrl = (abortRef.current = new AbortController());
      try {
        await streamChat(text, (t) => ty.push(t), ctrl.signal);
      } catch (err) {
        if (ctrl.signal.aborted) { ty.end(); return; }
        ty.push(err.userMessage || 'No pude conectar. Inténtalo de nuevo.');
      } finally {
        if (abortRef.current === ctrl) abortRef.current = null;
      }
      ty.end();
      await ty.done;
      setChatHistory((h) => h.map((m) => (m.id === botMsg.id ? { ...m, pending: false, done: true } : m)));
    } finally {
      setBusy(false);
      inputRef.current?.focus();
    }
  };

  const startLive = () => {
    if (busy || liveRef.current?.isActive()) return;
    dictation.cancel();
    liveRef.current?.start();
  };

  // Antes de abrir el modo live: materia del curso y archivo elegido pero sin enviar
  const beforeLive = async () => {
    await ensureSetup();
    if (selectedFile) {
      await uploadFile(selectedFile.file);
      clearSelectedFile();
    }
  };

  const onLiveEnd = (msg) => {
    if (msg) addChatMessage('bot', msg);
    inputRef.current?.focus();
  };

  const placeholder = dictation.state === 'rec' ? 'Grabando… toca el micrófono para terminar'
    : dictation.state === 'busy' ? 'Transcribiendo…'
    : selectedFile ? (selectedFile.isImage ? 'Pregunta sobre esta foto o pulsa Enviar…' : 'Pregunta sobre este archivo o pulsa Enviar…')
    : 'Escribe un mensaje...';

  return (
    <div className="app-container">

      {/* BOTÓN FLOTANTE Y BURBUJA INICIAL */}
      {!isOpen && (
        <div className="initial-trigger" onClick={openChat}>
          <div className="initial-bubble">¿Qué vamos a hacer hoy?</div>
          <div className="floating-btn">
            <img src={selectedAvatar} alt="EVA" className="eva-floating-image" />
          </div>
        </div>
      )}

      {/* VENTANA DEL CHAT */}
      {isOpen && (
        <div className={`chat-widget ${isExpanded ? 'expanded' : ''}`}>

          {/* Header - SOLO SE MUESTRA EN EL CHAT */}
          {currentScreen === 'chat' && (
            <div className="chat-header">
              <div className="chat-header-left">
                <div className="avatar-small blue-bg">
                  <img src={selectedAvatar} alt="Avatar" className="avatar-img" />
                </div>
                <span>EVA</span>
              </div>

              <div className="chat-header-icons">

                {/* MENÚ DE AJUSTES */}
                <div className="options-container" ref={menuContainerRef}>
                  <button
                    type="button"
                    className="icon-btn"
                    aria-label="Ajustes y opciones"
                    title="Ajustes y opciones"
                    aria-expanded={isMenuOpen}
                    onClick={() => setIsMenuOpen(!isMenuOpen)}
                  >
                    <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true">
                      <circle cx="12" cy="5" r="2"></circle>
                      <circle cx="12" cy="12" r="2"></circle>
                      <circle cx="12" cy="19" r="2"></circle>
                    </svg>
                  </button>

                  {isMenuOpen && (
                    <div className="menu-popup-wrapper">
                      <MenuAjustes
                        onNuevoChat={() => {
                          setIsMenuOpen(false);
                          newChat();
                        }}
                        onHistorial={() => {
                          setIsMenuOpen(false);
                          setCurrentScreen('history');
                        }}
                        onCerrarSesion={logout}
                      />
                    </div>
                  )}
                </div>

                <button
                  type="button"
                  className="icon-btn"
                  aria-label={isExpanded ? 'Reducir tamaño' : 'Expandir ventana'}
                  title={isExpanded ? 'Reducir tamaño' : 'Expandir ventana'}
                  onClick={() => setIsExpanded(!isExpanded)}
                >
                  <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                    {isExpanded ? (
                      <path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3" />
                    ) : (
                      <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" />
                    )}
                  </svg>
                </button>
                <button
                  type="button"
                  className="icon-btn"
                  aria-label="Cerrar chat"
                  title="Cerrar chat"
                  onClick={closeChat}
                >
                  <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                    <path d="M18 6L6 18M6 6l12 12"/>
                  </svg>
                </button>
              </div>
            </div>
          )}

          {/* CONTENEDOR DE PANTALLAS */}
          <div className="chat-content">

            {/* PANTALLA 1: BIENVENIDA */}
            {currentScreen === 'welcome' && (
              <div className="screen-content">
                <div className="avatar-large blue-bg">
                  <img src={eva} alt="EVA Básica" className="avatar-img-large" />
                </div>
                <h2>BIENVENIDO<br/>AL CHAT DE EVA</h2>
                <p>Tu asistente personal para gestionar tus tareas y finanzas.</p>
                <button className="btn-primary" onClick={() => setCurrentScreen('login')}>COMENZAR</button>
              </div>
            )}

            {/* PANTALLA 2: LOGIN */}
            {currentScreen === 'login' && (
              <form className="screen-content login-screen" onSubmit={handleLoginSubmit}>
                <div className="login-header">
                  <div className="avatar-medium blue-bg">
                    <img src={selectedAvatar} alt="EVA" className="avatar-img-large" />
                  </div>
                  <p>"Verifica tu identidad"</p>
                </div>

                <div className="input-group">
                  <label>Usuario</label>
                  <input
                    type="text"
                    inputMode="text"
                    pattern="[a-zA-Z0-9._\-]*"
                    placeholder="Ej: juan_123"
                    value={usuario}
                    onChange={handleUsernameInput}
                    onKeyDown={blockInvalidUsername}
                    autoComplete="username"
                  />
                </div>
                <div className="input-group">
                  <label>Código</label>
                  <input
                    type="password"
                    inputMode="numeric"
                    pattern="[0-9]*"
                    placeholder="••••••••"
                    value={codigo}
                    onChange={handleNumericInput(setCodigo)}
                    onKeyDown={blockNonNumeric}
                  />
                </div>

                <div className="input-group">
                  <label>Curso al que perteneces</label>
                  <select
                    value={curso}
                    onChange={(e) => {
                      setCurso(e.target.value);
                      startedRef.current = false;
                      setLoginError('');
                    }}
                    className="select-curso"
                  >
                    <option value="">Selecciona tu curso...</option>
                    {CURSOS.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
                  </select>
                </div>

                {loginError && <p className="login-error-text" role="alert">{loginError}</p>}

                <button type="submit" className="btn-primary mt-20">IR AL CHAT</button>
              </form>
            )}

            {/* PANTALLA 3: CARRUSEL */}
            {currentScreen === 'avatar-select' && (
              <div className="screen-content carousel-screen">
                <h2>Elige tu Avatar</h2>
                <p>Desliza o usa las flechas del control</p>

                <Suspense fallback={<div className="dots" style={{ padding: '60px 0' }}><i></i><i></i><i></i></div>}>
                  <AvatarPicker avatars={AVATARS} initialIndex={avatarIndex} onChange={setAvatarIndex} />
                </Suspense>

                <button
                  className="btn-primary mt-20"
                  onClick={() => {
                    lsSet(AVATAR_KEY, String(avatarIndex));
                    lsSet(SESSION_KEYS.loggedIn, '1');
                    setCurrentScreen('chat-ready');
                  }}
                >
                  CONFIRMAR AVATAR
                </button>
              </div>
            )}

            {/* PANTALLA 4: SALUDO */}
            {currentScreen === 'chat-ready' && (
              <div className="screen-content">
                <div className="avatar-large blue-bg">
                  <img src={selectedAvatar} alt="Avatar" className="avatar-img-large" />
                </div>
                <h2>¡EY {usuario ? `@${usuario}` : '@USUARIO'} BIENVENID@!</h2>
                <p>{curso ? `Perteneces al curso: ${cursoLabel}` : '¿Qué haremos hoy?'}</p>

                <div className="tags-container">
                  <label className="tag-upload">
                    {selectedFile ? `ADJUNTO: ${selectedFile.file.name}` : 'ADJUNTAR ARCHIVO'}
                    <input
                      type="file"
                      accept={FILE_ACCEPT}
                      onChange={(e) => pickFile(e.target.files[0])}
                      hidden
                    />
                  </label>
                  <span>ACTIVIDADES Y REUNIONES</span> {/* bueno acá es cuando ya este conectado a la api y los hilos tambien */}
                  <span>MENSAJES E HILOS</span>
                </div>
                {hint && <p className="text-xs !text-pink-600" role="alert">{hint}</p>}

                <button className="btn-primary" onClick={() => setCurrentScreen('chat')}>Empezar a chatear</button>
              </div>
            )}

            {/* PANTALLA NUEVA: HISTORIAL DE CHAT */}
            {currentScreen === 'history' && (
              <div className="screen-content history-screen">
                <h2>Historial de Chat</h2>
                <p>Tus conversaciones anteriores</p>

                <div className="history-list">
                  {chatHistory.some((m) => m.text) ? (
                    chatHistory.filter((m) => m.text).map((msg) => (
                      <div key={msg.id} className={`history-item ${msg.type}`}>
                        <strong>{msg.type === 'bot' ? 'EVA' : 'Tú'}:</strong> {msg.text}
                      </div>
                    ))
                  ) : (
                    <p>No hay historial aún.</p>
                  )}
                </div>

                <button className="btn-primary mt-20" onClick={() => setCurrentScreen('chat')}>
                  Volver al Chat
                </button>
              </div>
            )}

            {/* PANTALLA 5: CHAT ACTIVO */}
            {currentScreen === 'chat' && (
              <>
                <div className="chat-messages" ref={messagesRef} onScroll={onMessagesScroll} aria-live="polite">
                  {chatHistory.map((msg) => (
                    <MessageRow key={msg.id} msg={msg} say={say} showListen={msg.type === 'bot' && msg.done} />
                  ))}
                </div>

                {!livePopupOpen && (
                  <div className="flex flex-col">
                    {hint && <p className="px-5 pt-2 text-xs !text-pink-600" aria-live="polite">{hint}</p>}

                    {/* Vista previa de archivo adjunto */}
                    {selectedFile && (
                      <div className="flex items-center gap-2 mx-5 mt-2 px-3 py-1.5 bg-indigo-50/70 border border-solid border-indigo-100 rounded-xl text-xs text-slate-700">
                        {selectedFile.isImage
                          ? <img className="eva-thumb" src={selectedFile.url} alt="Vista previa de la imagen" />
                          : <svg className="size-4 shrink-0 text-[#2f5bea]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48" /></svg>}
                        <div className="flex-1 min-w-0">
                          <div className="truncate font-medium text-slate-800">{selectedFile.file.name}</div>
                          <div className="text-[10px] text-slate-400">{formatSize(selectedFile.file.size)}</div>
                        </div>
                        <button type="button" onClick={clearSelectedFile} aria-label="Quitar archivo adjunto" title="Quitar archivo"
                          className="p-0.5 bg-transparent border-0 cursor-pointer text-slate-400 hover:text-pink-600 rounded-md">
                          <svg className="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
                        </button>
                      </div>
                    )}

                    <form className="chat-input-area" onSubmit={handleSendMessage}>
                      <input ref={chatFileRef} type="file" accept={FILE_ACCEPT} hidden onChange={(e) => pickFile(e.target.files[0])} />
                      <button type="button" className="eva-tool" aria-label="Adjuntar archivo o imagen" title="Adjuntar archivo o imagen" onClick={() => chatFileRef.current?.click()}>
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48" /></svg>
                      </button>
                      <input
                        ref={inputRef}
                        type="text"
                        placeholder={placeholder}
                        value={message}
                        onChange={(e) => setMessage(e.target.value)}
                      />
                      {dictation.supported && (
                        <button type="button" className={'eva-tool' + (dictation.state === 'rec' ? ' rec' : '')} disabled={dictation.state === 'busy'}
                          aria-pressed={dictation.state === 'rec'} aria-label={dictation.state === 'rec' ? 'Detener dictado' : 'Dictar mensaje'}
                          title={dictation.state === 'rec' ? 'Detener dictado' : 'Dictar mensaje'} onClick={dictation.toggle}>
                          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><rect x="9" y="3" width="6" height="12" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" /></svg>
                        </button>
                      )}
                      <button type="button" className="eva-tool" aria-label="Hablar con Eva en vivo" title="Hablar con Eva en vivo" onClick={startLive}>
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M4 10v4M8 7v10M12 4v16M16 8v8M20 11v2" /></svg>
                      </button>
                      <button type="submit" disabled={busy} aria-label="Enviar">
                        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="white" strokeWidth="2"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>
                      </button>
                    </form>
                  </div>
                )}
              </>
            )}

          </div> {/* FIN DEL CONTENEDOR DE PANTALLAS */}

          <div className="chat-footer" onClick={closeChat}>
            Cerrar chat
          </div>
        </div>
      )}

      {/* MODO LIVE (EvaExplica): pop-up con Eva animada, fuera del widget para cubrir la pantalla */}
      <LiveMode
        ref={liveRef}
        avatarIndex={avatarIndex}
        avatarThumb={selectedAvatar}
        beforeStart={beforeLive}
        say={say}
        addChatMessage={addChatMessage}
        updateChatMessage={updateChatMessage}
        onEnd={onLiveEnd}
        onVisibleChange={setLivePopupOpen}
      />
    </div>
  );
}

export default App;
