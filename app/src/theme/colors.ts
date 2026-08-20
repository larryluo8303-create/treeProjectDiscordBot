/** Dark theme color palette. */
export const colors = {
  background: '#0f172a',
  surface: '#1e293b',
  surfaceHover: '#334155',
  border: '#334155',

  primary: '#3b82f6',
  primaryDark: '#2563eb',
  success: '#22c55e',
  warning: '#f59e0b',
  danger: '#ef4444',
  info: '#06b6d4',

  textPrimary: '#f1f5f9',
  textSecondary: '#94a3b8',
  textMuted: '#64748b',

  // Status colors
  statusOnline: '#22c55e',
  statusOffline: '#ef4444',
  statusPending: '#f59e0b',

  // Confidence colors
  confidenceHigh: '#22c55e',    // 8-10
  confidenceMedium: '#f59e0b',  // 5-7
  confidenceLow: '#ef4444',     // 1-4
} as const;

export function confidenceColor(score: number): string {
  if (score >= 8) return colors.confidenceHigh;
  if (score >= 5) return colors.confidenceMedium;
  return colors.confidenceLow;
}
