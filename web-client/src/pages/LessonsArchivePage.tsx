import { GraduationCap, Calendar, Loader2, AlertTriangle } from 'lucide-react';
import { useLessonArchive } from '../api/hooks';

export default function LessonsArchivePage() {
  const { data, isLoading, error } = useLessonArchive();

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
        <p className="text-danger">Failed to load lesson archive</p>
      </div>
    );
  }

  const items: Array<{ title: string; content: string; scheduled_at: string }> = data?.items || [];

  if (items.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-3 p-8">
        <GraduationCap size={64} className="text-text-muted" />
        <h2 className="text-xl font-bold text-text-main">No Past Lessons</h2>
        <p className="text-text-secondary text-sm">Completed lessons will appear here</p>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <h1 className="text-xl font-bold text-text-main mb-1">Lesson Archive</h1>
      <p className="text-text-secondary text-sm mb-6">
        {items.length} completed lesson{items.length !== 1 ? 's' : ''}
      </p>

      <div className="max-w-3xl space-y-3">
        {items.map((ls, i) => (
          <div key={i} className="bg-surface border border-border rounded-xl p-4">
            <div className="flex items-center gap-2 mb-2">
              <GraduationCap size={16} className="text-info" />
              <h3 className="text-text-main font-semibold text-sm flex-1">{ls.title}</h3>
            </div>
            <p className="text-text-secondary text-sm leading-relaxed mb-3">{ls.content}</p>
            <div className="flex items-center gap-1.5 text-text-muted text-xs">
              <Calendar size={12} />
              <span>{new Date(ls.scheduled_at).toLocaleDateString()}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
