// Una burbuja del chat. memo(): mientras Eva escribe solo se vuelve a pintar su burbuja, no toda la conversación.
import { memo } from 'react';
import ListenButton from './live/ListenButton';

function MessageRow({ msg, showListen, say }) {
  const a = msg.attachment;
  return (
    <div className={`message-row ${msg.type}`}>
      <div className={`message ${msg.type}`}>
        {a && (a.isImage && a.url ? (
          <div className="chat-image-wrap">
            <img src={a.url} alt={a.name || 'Foto enviada'} title="Haz clic para ver imagen en tamaño completo"
              onClick={() => window.open(a.url, '_blank', 'noopener,noreferrer')} />
          </div>
        ) : (
          <div className="inline-flex items-center gap-1.5 px-2.5 py-1 mb-1.5 bg-white/40 rounded-lg text-xs font-medium">
            <svg className="size-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48" /></svg>
            <span className="truncate max-w-[200px]">{a.name || 'Archivo adjunto'}</span>
          </div>
        ))}
        {msg.pending ? <span className="dots" aria-label="Eva está escribiendo"><i></i><i></i><i></i></span> : msg.text}
      </div>
      {showListen && <ListenButton id={msg.id} text={msg.text} say={say} />}
    </div>
  );
}

export default memo(MessageRow);
