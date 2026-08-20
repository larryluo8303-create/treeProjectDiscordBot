import { useState, useEffect } from 'react';
import { Bookmark, Trash2, HelpCircle } from 'lucide-react';
import { loadBookmarks, deleteBookmark, type Bookmark as BM } from '../utils/storage';
import { confidenceColor, confidenceBg, formatDate } from '../utils/helpers';

export default function BookmarksPage() {
  const [bookmarks, setBookmarks] = useState<BM[]>([]);

  useEffect(() => {
    setBookmarks(loadBookmarks());
  }, []);

  const handleDelete = (id: string) => {
    if (!confirm('Remove this saved answer?')) return;
    deleteBookmark(id);
    setBookmarks((prev) => prev.filter((b) => b.id !== id));
  };

  if (bookmarks.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-3 p-8">
        <Bookmark size={64} className="text-text-muted" />
        <h2 className="text-xl font-bold text-text-main">No Bookmarks</h2>
        <p className="text-text-secondary text-sm text-center">
          Tap the bookmark icon on any bot answer to save it here
        </p>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <h1 className="text-xl font-bold text-text-main mb-1">Bookmarks</h1>
      <p className="text-text-secondary text-sm mb-6">{bookmarks.length} saved answer{bookmarks.length !== 1 ? 's' : ''}</p>

      <div className="max-w-3xl space-y-3">
        {bookmarks.map((b) => (
          <div key={b.id} className="bg-surface border border-border rounded-xl p-4">
            <div className="flex items-center gap-2 mb-2">
              <HelpCircle size={14} className="text-primary shrink-0" />
              <span className="text-text-main text-sm font-semibold flex-1 line-clamp-1">{b.question}</span>
              <button onClick={() => handleDelete(b.id)} className="text-text-muted hover:text-danger transition-colors p-1">
                <Trash2 size={14} />
              </button>
            </div>
            <p className="text-text-secondary text-sm leading-relaxed mb-3">{b.answer}</p>
            <div className="flex items-center justify-between">
              <span className={`text-[11px] font-bold px-2 py-0.5 rounded ${confidenceBg(b.confidence)} ${confidenceColor(b.confidence)}`}>
                {b.confidence}/10
              </span>
              <span className="text-text-muted text-xs">{formatDate(b.savedAt)}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
