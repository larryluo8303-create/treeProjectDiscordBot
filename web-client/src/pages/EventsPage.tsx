import { CalendarDays, ExternalLink, GraduationCap, Repeat, Loader2, AlertTriangle } from 'lucide-react';
import { usePromos, useLessons } from '../api/hooks';

export default function EventsPage() {
  const promos = usePromos();
  const lessons = useLessons();

  if (promos.isLoading || lessons.isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 size={32} className="text-primary animate-spin" />
      </div>
    );
  }

  const promoItems: Array<{ title: string; description: string; url?: string; start_date?: string }> =
    promos.data?.items || [];
  const lessonItems: Array<{ title: string; content: string; scheduled_at: string; repeat?: string }> =
    lessons.data?.items || [];

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <h1 className="text-xl font-bold text-text-main mb-6">Events & Promotions</h1>

      {/* Promotions */}
      <div className="mb-8">
        <div className="flex items-center gap-2 mb-4">
          <CalendarDays size={18} className="text-warning" />
          <h2 className="text-lg font-semibold text-text-main">Upcoming Promotions</h2>
        </div>
        {promoItems.length === 0 ? (
          <p className="text-text-muted text-sm">No active promotions</p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {promoItems.map((p, i) => (
              <div key={i} className="bg-surface border border-border rounded-xl p-4">
                <h3 className="text-text-main font-semibold text-sm mb-1">{p.title}</h3>
                <p className="text-text-secondary text-sm mb-3 leading-relaxed">{p.description}</p>
                <div className="flex items-center justify-between">
                  {p.start_date && <span className="text-text-muted text-xs">{new Date(p.start_date).toLocaleDateString()}</span>}
                  {p.url && (
                    <a href={p.url} target="_blank" rel="noreferrer" className="text-primary text-xs flex items-center gap-1 hover:underline">
                      Details <ExternalLink size={12} />
                    </a>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Lessons */}
      <div>
        <div className="flex items-center gap-2 mb-4">
          <GraduationCap size={18} className="text-info" />
          <h2 className="text-lg font-semibold text-text-main">Upcoming Lessons</h2>
        </div>
        {lessonItems.length === 0 ? (
          <p className="text-text-muted text-sm">No upcoming lessons</p>
        ) : (
          <div className="space-y-3">
            {lessonItems.map((ls, i) => (
              <div key={i} className="bg-surface border border-border rounded-xl p-4">
                <div className="flex items-center gap-2 mb-1">
                  <h3 className="text-text-main font-semibold text-sm">{ls.title}</h3>
                  {ls.repeat && (
                    <span className="text-accent text-[10px] font-semibold bg-accent/20 px-1.5 py-0.5 rounded flex items-center gap-0.5">
                      <Repeat size={10} /> {ls.repeat}
                    </span>
                  )}
                </div>
                <p className="text-text-secondary text-sm mb-2 leading-relaxed">{ls.content}</p>
                <span className="text-text-muted text-xs">{new Date(ls.scheduled_at).toLocaleDateString()}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
