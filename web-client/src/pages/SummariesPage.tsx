import { useState } from 'react';
import { FileText, Calendar, MessageSquare, Loader2, AlertTriangle, Sun, CalendarDays } from 'lucide-react';
import { useSummaries, SummaryItem } from '../api/hooks';

type FilterType = 'all' | 'daily' | 'weekly';

export default function SummariesPage() {
  const [filter, setFilter] = useState<FilterType>('all');
  const queryType = filter === 'all' ? undefined : filter;
  const { data, isLoading, error } = useSummaries(queryType);

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 size={32} className="text-primary animate-spin" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-3">
        <AlertTriangle size={48} className="text-danger" />
        <p className="text-danger">Failed to load summaries</p>
      </div>
    );
  }

  const items: SummaryItem[] = data?.items || [];

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <h1 className="text-xl font-bold text-text-main mb-1">Summaries</h1>
      <p className="text-text-secondary text-sm mb-4">AI-generated daily & weekly summaries</p>

      {/* Filter buttons */}
      <div className="flex gap-2 mb-6">
        {(['all', 'daily', 'weekly'] as const).map((t) => (
          <button
            key={t}
            onClick={() => setFilter(t)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              filter === t
                ? 'bg-primary text-white'
                : 'bg-surface border border-border text-text-secondary hover:text-text-main'
            }`}
          >
            {t === 'all' ? 'All' : t === 'daily' ? 'Daily' : 'Weekly'}
          </button>
        ))}
      </div>

      {items.length === 0 ? (
        <div className="flex flex-col items-center mt-12 gap-3">
          <FileText size={64} className="text-text-muted" />
          <h2 className="text-lg font-bold text-text-main">No Summaries Yet</h2>
          <p className="text-text-secondary text-sm">Summaries will appear here after they are generated</p>
        </div>
      ) : (
        <div className="max-w-3xl space-y-4">
          {items.map((item, i) => (
            <div key={i} className="bg-surface border border-border rounded-xl p-5">
              <div className="flex items-center gap-2 mb-3">
                {item.type === 'daily' ? (
                  <Sun size={16} className="text-warning shrink-0" />
                ) : (
                  <CalendarDays size={16} className="text-info shrink-0" />
                )}
                <h3 className="text-text-main font-semibold text-sm flex-1">{item.title}</h3>
                <span className={`text-[10px] font-semibold px-2 py-0.5 rounded ${
                  item.type === 'daily'
                    ? 'bg-warning/20 text-warning'
                    : 'bg-info/20 text-info'
                }`}>
                  {item.type === 'daily' ? 'Daily' : 'Weekly'}
                </span>
              </div>

              <div className="text-text-secondary text-sm leading-relaxed mb-3 whitespace-pre-wrap">
                {item.content}
              </div>

              <div className="flex items-center gap-4 text-text-muted text-xs">
                <div className="flex items-center gap-1">
                  <Calendar size={12} />
                  <span>{new Date(item.timestamp).toLocaleString()}</span>
                </div>
                <div className="flex items-center gap-1">
                  <MessageSquare size={12} />
                  <span>{item.message_count} messages</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
