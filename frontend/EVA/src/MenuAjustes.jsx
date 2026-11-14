import { useEffect, useState } from 'react';
import './MenuAjustes.css';

/* ---------- Íconos SVG ---------- */
const Icono = ({ children, size = 18, className }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    aria-hidden="true"
  >
    {children}
  </svg>
);

const IconoMas = (p) => (
  <Icono {...p}>
    <path d="M12 5v14M5 12h14" />
  </Icono>
);

const IconoLuna = (p) => (
  <Icono {...p}>
    <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
  </Icono>
);

const IconoTexto = (p) => (
  <Icono {...p}>
    <path d="M4 7V5h16v2M12 5v14M9 19h6" />
  </Icono>
);

const IconoReloj = (p) => (
  <Icono {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7v5l3 2" />
  </Icono>
);

const IconoSalir = (p) => (
  <Icono {...p}>
    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
    <polyline points="16 17 21 12 16 7" />
    <line x1="21" y1="12" x2="9" y2="12" />
  </Icono>
);

const IconoFlecha = (p) => (
  <Icono {...p}>
    <path d="M9 6l6 6-6 6" />
  </Icono>
);

/* ---------- Lectura de preferencias guardadas ---------- */
const leer = (clave, defecto) => {
  try {
    return localStorage.getItem(clave) || defecto;
  } catch {
    return defecto;
  }
};

const OPCIONES_TAMANO = [
  { id: 'pequena', label: 'Pequeña' },
  { id: 'mediana', label: 'Mediana' },
  { id: 'grande', label: 'Grande' },
];

export default function MenuAjustes({ onNuevoChat, onHistorial, onCerrarSesion }) {
  const [oscuro, setOscuro] = useState(() => leer('tema', 'claro') === 'oscuro');
  const [tamano, setTamano] = useState(() => leer('tamano', 'mediana'));

  // Aplica el tema a toda la app
  useEffect(() => {
    const valor = oscuro ? 'oscuro' : 'claro';
    document.documentElement.setAttribute('data-tema', valor);
    try {
      localStorage.setItem('tema', valor);
    } catch {
      // Almacenamiento bloqueado o modo privado
    }
  }, [oscuro]);

  // Aplica el tamaño de letra a toda la app
  useEffect(() => {
    document.documentElement.setAttribute('data-tamano', tamano);
    try {
      localStorage.setItem('tamano', tamano);
    } catch {
      // Almacenamiento bloqueado o modo privado
    }
  }, [tamano]);

  return (
    <div className="menu">
      <button type="button" className="menu-item" onClick={onNuevoChat}>
        <IconoMas />
        <span>Nuevo chat</span>
      </button>

      <div className="menu-divisor" />

      <div className="menu-item menu-item-fijo">
        <IconoLuna />
        <span>Tema oscuro</span>
        <button
          type="button"
          role="switch"
          aria-checked={oscuro}
          aria-label="Tema oscuro"
          className={`switch ${oscuro ? 'on' : ''}`}
          onClick={() => setOscuro((v) => !v)}
        >
          <span className="switch-bola" />
        </button>
      </div>

      <div className="menu-grupo">
        <div className="menu-grupo-titulo">
          <IconoTexto />
          <strong>Tamaño</strong>
        </div>
        <div className="segmentado" role="radiogroup" aria-label="Tamaño de letra">
          {OPCIONES_TAMANO.map((o) => (
            <button
              key={o.id}
              type="button"
              role="radio"
              aria-checked={tamano === o.id}
              className={tamano === o.id ? 'activo' : ''}
              onClick={() => setTamano(o.id)}
            >
              {o.label}
            </button>
          ))}
        </div>
      </div>

      <div className="menu-divisor" />

      <button type="button" className="menu-item" onClick={onHistorial}>
        <IconoReloj />
        <span>Historial de chat</span>
        <IconoFlecha size={16} className="menu-flecha" />
      </button>

      {onCerrarSesion && (
        <>
          <div className="menu-divisor" />
          <button type="button" className="menu-item menu-item-danger" onClick={onCerrarSesion}>
            <IconoSalir />
            <span>Cerrar sesión</span>
          </button>
        </>
      )}
    </div>
  );
}
