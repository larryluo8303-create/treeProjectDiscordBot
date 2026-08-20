import { describe, it, expect } from 'vitest';
import { Colors, confidenceColor } from '../theme/colors';

describe('Colors palette', () => {
  it('exports all required color tokens', () => {
    expect(Colors.background).toBe('#0F1419');
    expect(Colors.surface).toBe('#1A2332');
    expect(Colors.primary).toBe('#3B82F6');
    expect(Colors.success).toBe('#10B981');
    expect(Colors.warning).toBe('#F59E0B');
    expect(Colors.danger).toBe('#EF4444');
    expect(Colors.text).toBe('#F1F5F9');
    expect(Colors.border).toBe('#334155');
  });

  it('exports hex color format for all values', () => {
    Object.values(Colors).forEach((c) => {
      expect(c).toMatch(/^#[0-9A-Fa-f]{6}$/);
    });
  });
});

describe('confidenceColor', () => {
  it('returns success color for high scores (8-10)', () => {
    expect(confidenceColor(8)).toBe(Colors.success);
    expect(confidenceColor(9)).toBe(Colors.success);
    expect(confidenceColor(10)).toBe(Colors.success);
  });

  it('returns warning color for medium scores (5-7)', () => {
    expect(confidenceColor(5)).toBe(Colors.warning);
    expect(confidenceColor(6)).toBe(Colors.warning);
    expect(confidenceColor(7)).toBe(Colors.warning);
  });

  it('returns danger color for low scores (1-4)', () => {
    expect(confidenceColor(1)).toBe(Colors.danger);
    expect(confidenceColor(4)).toBe(Colors.danger);
    expect(confidenceColor(0)).toBe(Colors.danger);
  });
});
