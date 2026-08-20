import { useState } from 'react';
import { Newspaper, AlertTriangle, Loader2, Star, ExternalLink } from 'lucide-react';
import { useNews, type NewsItem } from '../api/hooks';

type Filter = 'all' | 'important';

export default function NewsPage() {
  const { data, isLoading, error } = useNews(80);
  const [filter, setFilter] = useState<Filter>('all');

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
        <p className="text-danger">Failed to load market news</p>
      </div>
    );
  }

  const allItems: NewsItem[] = data?.items ?? [];
  const items = filter === 'important' ? allItems.filter((n) => n.important) : allItems;

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-xl font-bold text-text-main mb-1">Market News</h1>
          <p className="text-text-secondary text-sm">Real-time market flash news, auto-refreshing every 30s</p>
        </div>
        <div className="flex gap-1 bg-surface border border-border rounded-lg p-0.5">
          <button
            onClick={() => setFilter('all')}
            className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
              filter === 'all'
                ? 'bg-primary text-white'
                : 'text-text-secondary hover:text-text-main'
            }`}
          >
            All
          </button>
          <button
            onClick={() => setFilter('important')}
            className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
              filter === 'important'
                ? 'bg-danger text-white'
                : 'text-text-secondary hover:text-text-main'
            }`}
          >
            Important
          </button>
        </div>
      </div>

      {items.length === 0 ? (
        <div className="flex flex-col items-center mt-16 gap-3">
          <Newspaper size={48} className="text-text-muted" />
          <p className="text-text-muted">No news available</p>
        </div>
      ) : (
        <div className="space-y-3">
          {items.map((item) => (
            <NewsCard key={item.id} item={item} />
          ))}
        </div>
      )}
    </div>
  );
}

function NewsCard({ item }: { item: NewsItem }) {
  const [imgError, setImgError] = useState(false);

  return (
    <div
      className={`bg-surface border rounded-xl p-4 ${
        item.important ? 'border-danger/40' : 'border-border'
      }`}
    >
      <div className="flex items-start gap-3">
        {item.important && (
          <Star size={16} className="text-danger shrink-0 mt-0.5 fill-danger" />
        )}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <h3 className={`font-semibold text-sm leading-tight ${
              item.important ? 'text-danger' : 'text-text-main'
            }`}>
              {item.title}
            </h3>
          </div>

          {item.body && item.body !== item.title && (
            <p className="text-text-secondary text-sm leading-relaxed whitespace-pre-line mt-1">
              {item.body}
            </p>
          )}

          {item.pic && !imgError && (
            <div className="mt-2 rounded-lg overflow-hidden max-w-md">
              <img
                src={item.pic}
                alt=""
                className="w-full h-auto"
                onError={() => setImgError(true)}
                loading="lazy"
              />
            </div>
          )}

          <div className="flex items-center gap-3 mt-2">
            <span className="text-text-muted text-xs">{item.time}</span>
            {item.link && (
              <a
                href={item.link}
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary text-xs flex items-center gap-1 hover:underline"
              >
                <ExternalLink size={12} />
                Details
              </a>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
