import { useState } from 'react';
import { ChevronDown, ChevronRight, HelpCircle, Loader2, AlertTriangle } from 'lucide-react';
import { useFAQ } from '../api/hooks';

export default function FAQPage() {
  const { data, isLoading, error } = useFAQ();
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  const toggle = (i: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });
  };

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
        <p className="text-danger">Failed to load FAQ</p>
      </div>
    );
  }

  const items: Array<{ question: string; answer: string }> = data?.items || [];

  if (items.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-3">
        <HelpCircle size={64} className="text-text-muted" />
        <p className="text-text-muted">No FAQ items yet</p>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <h1 className="text-xl font-bold text-text-main mb-1">FAQ</h1>
      <p className="text-text-secondary text-sm mb-6">Frequently asked questions</p>

      <div className="max-w-3xl space-y-2">
        {items.map((item, i) => (
          <div key={i} className="bg-surface border border-border rounded-xl overflow-hidden">
            <button
              onClick={() => toggle(i)}
              className="w-full flex items-center gap-3 px-4 py-3.5 text-left hover:bg-surface-light transition-colors"
            >
              {expanded.has(i) ? (
                <ChevronDown size={16} className="text-primary shrink-0" />
              ) : (
                <ChevronRight size={16} className="text-text-muted shrink-0" />
              )}
              <span className="text-text-main text-sm font-medium">{item.question}</span>
            </button>
            {expanded.has(i) && (
              <div className="px-4 pb-4 pl-11">
                <p className="text-text-secondary text-sm leading-relaxed">{item.answer}</p>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
