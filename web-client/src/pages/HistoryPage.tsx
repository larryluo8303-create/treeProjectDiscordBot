import { useState, useEffect } from 'react';
import { History, MessageSquare, XCircle } from 'lucide-react';
import { loadSessions, deleteSession, type ChatSession } from '../utils/storage';
import { formatDate } from '../utils/helpers';

export default function HistoryPage() {
  const [sessions, setSessions] = useState<ChatSession[]>([]);

  useEffect(() => {
    setSessions(loadSessions());
  }, []);

  const handleDelete = (id: string) => {
    if (!confirm('Remove this chat session?')) return;
    deleteSession(id);
    setSessions((prev) => prev.filter((s) => s.id !== id));
  };

  if (sessions.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-3 p-8">
        <History size={64} className="text-text-muted" />
        <h2 className="text-xl font-bold text-text-main">No Chat History</h2>
        <p className="text-text-secondary text-sm text-center">Your past conversations will appear here</p>
      </div>
    );
  }

  const grouped: Record<string, ChatSession[]> = {};
  sessions.forEach((s) => {
    const key = formatDate(s.updatedAt);
    if (!grouped[key]) grouped[key] = [];
    grouped[key].push(s);
  });

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <h1 className="text-xl font-bold text-text-main mb-1">Chat History</h1>
      <p className="text-text-secondary text-sm mb-6">{sessions.length} conversation{sessions.length !== 1 ? 's' : ''}</p>

      <div className="max-w-3xl space-y-4">
        {Object.entries(grouped).map(([date, items]) => (
          <div key={date}>
            <h3 className="text-text-secondary text-xs font-semibold mb-2">{date}</h3>
            <div className="space-y-2">
              {items.map((s) => (
                <div key={s.id} className="bg-surface border border-border rounded-xl p-3 flex items-center gap-3">
                  <MessageSquare size={16} className="text-primary shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-text-main text-sm font-semibold truncate">{s.title}</p>
                    <p className="text-text-muted text-xs mt-0.5">
                      {s.messages.length} message{s.messages.length !== 1 ? 's' : ''} ·{' '}
                      {new Date(s.updatedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </p>
                  </div>
                  <button onClick={() => handleDelete(s.id)} className="text-text-muted hover:text-danger transition-colors p-1">
                    <XCircle size={16} />
                  </button>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
