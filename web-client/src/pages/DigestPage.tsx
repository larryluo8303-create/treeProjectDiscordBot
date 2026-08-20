import { MessageSquare, Zap, BarChart3, TrendingUp, Moon, AlertTriangle, Loader2 } from 'lucide-react';
import { useDigest } from '../api/hooks';

export default function DigestPage() {
  const { data, isLoading, error } = useDigest();

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
        <p className="text-danger">Failed to load digest</p>
      </div>
    );
  }

  const total = data?.total_queries ?? 0;
  const autoReplies = data?.auto_replies ?? 0;
  const avgConf = data?.avg_confidence ?? 0;
  const topQuestions: string[] = data?.top_questions ?? [];

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <h1 className="text-xl font-bold text-text-main mb-1">Daily Digest</h1>
      <p className="text-text-secondary text-sm mb-6">Last 24 hours activity summary</p>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
        <div className="bg-surface border border-border rounded-xl p-5 flex flex-col items-center gap-2">
          <MessageSquare size={24} className="text-primary" />
          <span className="text-3xl font-bold text-text-main">{total}</span>
          <span className="text-text-secondary text-xs">Queries</span>
        </div>
        <div className="bg-surface border border-border rounded-xl p-5 flex flex-col items-center gap-2">
          <Zap size={24} className="text-success" />
          <span className="text-3xl font-bold text-text-main">{autoReplies}</span>
          <span className="text-text-secondary text-xs">Auto Replies</span>
        </div>
        <div className="bg-surface border border-border rounded-xl p-5 flex flex-col items-center gap-2">
          <BarChart3 size={24} className="text-warning" />
          <span className="text-3xl font-bold text-text-main">{avgConf}</span>
          <span className="text-text-secondary text-xs">Avg Confidence</span>
        </div>
      </div>

      {topQuestions.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-4">
            <TrendingUp size={20} className="text-info" />
            <h2 className="text-lg font-bold text-text-main">Top Questions</h2>
          </div>
          <div className="space-y-2">
            {topQuestions.map((q: string, i: number) => (
              <div key={i} className="flex items-start gap-3 bg-surface border border-border rounded-xl p-3">
                <span className="text-primary font-bold text-sm w-6 text-center shrink-0">{i + 1}</span>
                <p className="text-text-main text-sm leading-relaxed">{q}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {total === 0 && (
        <div className="flex flex-col items-center mt-12 gap-3">
          <Moon size={48} className="text-text-muted" />
          <p className="text-text-muted">No activity in the last 24 hours</p>
        </div>
      )}
    </div>
  );
}
