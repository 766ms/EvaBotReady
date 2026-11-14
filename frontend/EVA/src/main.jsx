import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import './tailwind.css'
import App from './App.jsx'

// Aplicar tema y tamaño guardados desde el inicio en toda la app y el modo Live
try {
  const tema = localStorage.getItem('tema') || 'claro';
  document.documentElement.setAttribute('data-tema', tema);
  const tamano = localStorage.getItem('tamano') || 'mediana';
  document.documentElement.setAttribute('data-tamano', tamano);
} catch {
  // Almacenamiento bloqueado o modo privado
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
