import { describe, it, expect, beforeEach } from 'vitest';
import {
  loadSessions,
  saveCurrentSession,
  deleteSession,
  loadBookmarks,
  saveBookmark,
  deleteBookmark,
  type ChatSession,
  type Bookmark,
} from '../utils/storage';

beforeEach(() => {
  localStorage.clear();
});

// ---------- Chat Sessions ----------

describe('Chat Sessions', () => {
  const makeSession = (id: string, msgCount = 1): ChatSession => ({
    id,
    title: `Session ${id}`,
    messages: Array.from({ length: msgCount }, (_, i) => ({
      role: 'user' as const,
      content: `msg ${i}`,
      timestamp: Date.now(),
    })),
    createdAt: Date.now(),
    updatedAt: Date.now(),
  });

  it('loadSessions returns empty array when no data', () => {
    expect(loadSessions()).toEqual([]);
  });

  it('saveCurrentSession creates a new session', () => {
    const s = makeSession('a');
    saveCurrentSession(s);
    const loaded = loadSessions();
    expect(loaded).toHaveLength(1);
    expect(loaded[0].id).toBe('a');
  });

  it('saveCurrentSession updates existing session by id', () => {
    const s = makeSession('a');
    saveCurrentSession(s);
    const updated = { ...s, title: 'Updated' };
    saveCurrentSession(updated);
    const loaded = loadSessions();
    expect(loaded).toHaveLength(1);
    expect(loaded[0].title).toBe('Updated');
  });

  it('saveCurrentSession prepends new sessions', () => {
    saveCurrentSession(makeSession('a'));
    saveCurrentSession(makeSession('b'));
    const loaded = loadSessions();
    expect(loaded[0].id).toBe('b');
    expect(loaded[1].id).toBe('a');
  });

  it('saveCurrentSession caps at 50 sessions', () => {
    for (let i = 0; i < 55; i++) {
      saveCurrentSession(makeSession(`s${i}`));
    }
    expect(loadSessions()).toHaveLength(50);
  });

  it('deleteSession removes the specified session', () => {
    saveCurrentSession(makeSession('a'));
    saveCurrentSession(makeSession('b'));
    deleteSession('a');
    const loaded = loadSessions();
    expect(loaded).toHaveLength(1);
    expect(loaded[0].id).toBe('b');
  });

  it('deleteSession with nonexistent id does nothing', () => {
    saveCurrentSession(makeSession('a'));
    deleteSession('nonexistent');
    expect(loadSessions()).toHaveLength(1);
  });

  it('loadSessions returns empty array on corrupt JSON', () => {
    localStorage.setItem('bigtree_chat_history', '{invalid json');
    expect(loadSessions()).toEqual([]);
  });
});

// ---------- Bookmarks ----------

describe('Bookmarks', () => {
  const makeBookmark = (id: string): Bookmark => ({
    id,
    question: `Question ${id}`,
    answer: `Answer ${id}`,
    confidence: 8,
    savedAt: Date.now(),
  });

  it('loadBookmarks returns empty array when no data', () => {
    expect(loadBookmarks()).toEqual([]);
  });

  it('saveBookmark adds a bookmark', () => {
    saveBookmark(makeBookmark('b1'));
    const loaded = loadBookmarks();
    expect(loaded).toHaveLength(1);
    expect(loaded[0].id).toBe('b1');
  });

  it('saveBookmark prepends (newest first)', () => {
    saveBookmark(makeBookmark('b1'));
    saveBookmark(makeBookmark('b2'));
    const loaded = loadBookmarks();
    expect(loaded[0].id).toBe('b2');
    expect(loaded[1].id).toBe('b1');
  });

  it('saveBookmark caps at 100 bookmarks', () => {
    for (let i = 0; i < 105; i++) {
      saveBookmark(makeBookmark(`b${i}`));
    }
    expect(loadBookmarks()).toHaveLength(100);
  });

  it('deleteBookmark removes the specified bookmark', () => {
    saveBookmark(makeBookmark('b1'));
    saveBookmark(makeBookmark('b2'));
    deleteBookmark('b1');
    const loaded = loadBookmarks();
    expect(loaded).toHaveLength(1);
    expect(loaded[0].id).toBe('b2');
  });

  it('deleteBookmark with nonexistent id does nothing', () => {
    saveBookmark(makeBookmark('b1'));
    deleteBookmark('nonexistent');
    expect(loadBookmarks()).toHaveLength(1);
  });

  it('loadBookmarks returns empty array on corrupt JSON', () => {
    localStorage.setItem('bigtree_bookmarks', 'bad data');
    expect(loadBookmarks()).toEqual([]);
  });
});
