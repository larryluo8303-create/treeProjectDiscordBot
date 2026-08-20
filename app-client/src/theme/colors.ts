export const Colors = {
  background: '#0F1419',
  surface: '#1A2332',
  surfaceLight: '#243447',
  primary: '#3B82F6',
  primaryDark: '#2563EB',
  success: '#10B981',
  warning: '#F59E0B',
  danger: '#EF4444',
  info: '#06B6D4',
  text: '#F1F5F9',
  textSecondary: '#94A3B8',
  textMuted: '#64748B',
  border: '#334155',
  inputBg: '#1E293B',
  userBubble: '#3B82F6',
  botBubble: '#1E293B',
  accent: '#8B5CF6',
};

export function confidenceColor(score: number): string {
  if (score >= 8) return Colors.success;
  if (score >= 5) return Colors.warning;
  return Colors.danger;
}
