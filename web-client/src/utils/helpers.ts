export function confidenceColor(score: number): string {
  if (score >= 8) return 'text-success';
  if (score >= 5) return 'text-warning';
  return 'text-danger';
}

export function confidenceBg(score: number): string {
  if (score >= 8) return 'bg-success/20';
  if (score >= 5) return 'bg-warning/20';
  return 'bg-danger/20';
}

export function formatTime(ts: number): string {
  return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export function formatDate(ts: number): string {
  return new Date(ts).toLocaleDateString();
}
