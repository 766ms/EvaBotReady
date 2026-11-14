// Botón "Escuchar" junto a cada respuesta de Eva (la lógica está en listen.js)
import { useSyncExternalStore } from 'react';
import { LISTEN_LABEL, getSnapshot, listen, subscribe } from './listen';

export default function ListenButton({ id, text, say }) {
  const snap = useSyncExternalStore(subscribe, getSnapshot);
  const state = snap.id === id ? snap.state : 'idle';
  if (!text.trim()) return null;
  return (
    <button type="button" className="listen" data-state={state} aria-label={LISTEN_LABEL[state]} title={LISTEN_LABEL[state]}
      onClick={() => listen(id, text, say)}>
      <svg className="lis-play" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M11 5 6 9H2v6h4l5 4V5z" /><path d="M15.5 8.5a5 5 0 0 1 0 7M19 5a10 10 0 0 1 0 14" /></svg>
      <svg className="lis-stop" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><rect x="6" y="6" width="12" height="12" rx="2" /></svg>
      <span className="lis-load" aria-hidden="true" />
    </button>
  );
}
