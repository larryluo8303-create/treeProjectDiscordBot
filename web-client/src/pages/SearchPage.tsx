import { useState } from 'react';
import { Search, Loader2, FileText } from 'lucide-react';
import { useKBSearch } from '../api/hooks';

export default function SearchPage() {
  const [query, setQuery] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const { data, isLoading } = useKBSearch(searchTerm);

  const handleSearch = () => {
    if (query.trim()) setSearchTerm(query.trim());
  };

  const results: Array<{ text: string; score: number; type: string }> = data?.results || [];

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <h1 className="text-xl font-bold text-text-main mb-1">Knowledge Base Search</h1>
      <p className="text-text-secondary text-sm mb-6">Search through BigTree's knowledge base</p>

      <div className="flex gap-2 mb-6 max-w-2xl">
        <div className="flex-1 relative">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            placeholder="Search knowledge base..."
            className="w-full bg-input-bg border border-border rounded-xl pl-10 pr-4 py-2.5 text-text-main text-sm focus:outline-none focus:border-primary placeholder:text-text-muted"
          />
        </div>
        <button
          onClick={handleSearch}
          disabled={!query.trim()}
          className="px-5 py-2.5 bg-primary text-white rounded-xl text-sm font-medium disabled:opacity-40 hover:bg-primary-dark transition-colors"
        >
          Search
        </button>
      </div>

      {isLoading && (
        <div className="flex items-center gap-2">
          <Loader2 size={16} className="text-primary animate-spin" />
          <span className="text-text-secondary text-sm">Searching...</span>
        </div>
      )}

      {!isLoading && searchTerm && results.length === 0 && (
        <p className="text-text-muted text-sm">No results found for "{searchTerm}"</p>
      )}

      <div className="space-y-3 max-w-3xl">
        {results.map((r, i) => (
          <div key={i} className="bg-surface border border-border rounded-xl p-4">
            <div className="flex items-center gap-2 mb-2">
              <FileText size={14} className="text-info" />
              <span className="text-info text-xs font-semibold bg-info/20 px-2 py-0.5 rounded">{r.type || 'doc'}</span>
              <span className="text-text-muted text-xs ml-auto">Score: {(r.score * 100).toFixed(0)}%</span>
            </div>
            <p className="text-text-main text-sm leading-relaxed">{r.text}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
