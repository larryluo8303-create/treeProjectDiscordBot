import { describe, it, expect } from 'vitest';
import { confidenceColor, confidenceBg, formatTime, formatDate } from '../utils/helpers';

describe('confidenceColor', () => {
  it('returns success for high scores (8-10)', () => {
    expect(confidenceColor(8)).toBe('text-success');
    expect(confidenceColor(9)).toBe('text-success');
    expect(confidenceColor(10)).toBe('text-success');
  });

  it('returns warning for medium scores (5-7)', () => {
    expect(confidenceColor(5)).toBe('text-warning');
    expect(confidenceColor(6)).toBe('text-warning');
    expect(confidenceColor(7)).toBe('text-warning');
  });

  it('returns danger for low scores (1-4)', () => {
    expect(confidenceColor(1)).toBe('text-danger');
    expect(confidenceColor(4)).toBe('text-danger');
    expect(confidenceColor(0)).toBe('text-danger');
  });
});

describe('confidenceBg', () => {
  it('returns success bg for high scores', () => {
    expect(confidenceBg(8)).toBe('bg-success/20');
    expect(confidenceBg(10)).toBe('bg-success/20');
  });

  it('returns warning bg for medium scores', () => {
    expect(confidenceBg(5)).toBe('bg-warning/20');
    expect(confidenceBg(7)).toBe('bg-warning/20');
  });

  it('returns danger bg for low scores', () => {
    expect(confidenceBg(1)).toBe('bg-danger/20');
    expect(confidenceBg(4)).toBe('bg-danger/20');
  });
});

describe('formatTime', () => {
  it('returns a formatted time string', () => {
    const ts = new Date(2026, 0, 15, 14, 30, 0).getTime();
    const result = formatTime(ts);
    // Should contain hour and minute
    expect(result).toMatch(/\d{1,2}:\d{2}/);
  });

  it('handles midnight', () => {
    const ts = new Date(2026, 0, 1, 0, 0, 0).getTime();
    const result = formatTime(ts);
    expect(result).toMatch(/\d{1,2}:\d{2}/);
  });
});

describe('formatDate', () => {
  it('returns a formatted date string', () => {
    const ts = new Date(2026, 7, 13).getTime();
    const result = formatDate(ts);
    // Should contain date components
    expect(result).toBeTruthy();
    expect(typeof result).toBe('string');
    expect(result.length).toBeGreaterThan(0);
  });
});
