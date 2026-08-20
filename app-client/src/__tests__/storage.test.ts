import { describe, it, expect, beforeEach, vi } from 'vitest';

// Mock AsyncStorage before importing modules that use it
const store: Record<string, string> = {};
vi.mock('@react-native-async-storage/async-storage', () => ({
  default: {
    getItem: vi.fn((key: string) => Promise.resolve(store[key] ?? null)),
    setItem: vi.fn((key: string, value: string) => {
      store[key] = value;
      return Promise.resolve();
    }),
    removeItem: vi.fn((key: string) => {
      delete store[key];
      return Promise.resolve();
    }),
  },
}));

import {
  loadSessions,
  saveCurrentSession,
  deleteSession,
  loadBookmarks,
  saveBookmark,
  deleteBookmark,
  loadServerConfig,
  saveServerConfig,
  type ChatSession,
  type Bookmark,
} from '../utils/storage';

beforeEach(() => {
  Object.keys(store).forEach((k) => delete store[k]);
});

// ---- Chat Sessions ----

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

  it('loadSessions returns empty when no data', async () => {
    expect(await loadSessions()).toEqual([]);
  });

  it('saveCurrentSession creates and retrieves', async () => {
    await saveCurrentSession(makeSession('a'));
    const loaded = await loadSessions();
    expect(loaded).toHaveLength(1);
    expect(loaded[0].id).toBe('a');
  });

  it('saveCurrentSession updates existing session', async () => {
    await saveCurrentSession(makeSession('a'));
    await saveCurrentSession({ ...makeSession('a'), title: 'Updated' });
    const loaded = await loadSessions();
    expect(loaded).toHaveLength(1);
    expect(loaded[0].title).toBe('Updated');
  });

  it('saveCurrentSession prepends new sessions', async () => {
    await saveCurrentSession(makeSession('a'));
    await saveCurrentSession(makeSession('b'));
    const loaded = await loadSessions();
    expect(loaded[0].id).toBe('b');
  });

  it('saveCurrentSession caps at 50', async () => {
    for (let i = 0; i < 55; i++) {
      await saveCurrentSession(makeSession(`s${i}`));
    }
    expect(await loadSessions()).toHaveLength(50);
  });

  it('deleteSession removes session', async () => {
    await saveCurrentSession(makeSession('a'));
    await saveCurrentSession(makeSession('b'));
    await deleteSession('a');
    const loaded = await loadSessions();
    expect(loaded).toHaveLength(1);
    expect(loaded[0].id).toBe('b');
  });

  it('deleteSession with nonexistent id is no-op', async () => {
    await saveCurrentSession(makeSession('a'));
    await deleteSession('nope');
    expect(await loadSessions()).toHaveLength(1);
  });
});

// ---- Bookmarks ----

describe('Bookmarks', () => {
  const makeBookmark = (id: string): Bookmark => ({
    id,
    question: `Q ${id}`,
    answer: `A ${id}`,
    confidence: 7,
    savedAt: Date.now(),
  });

  it('loadBookmarks returns empty when no data', async () => {
    expect(await loadBookmarks()).toEqual([]);
  });

  it('saveBookmark adds a bookmark', async () => {
    await saveBookmark(makeBookmark('b1'));
    const loaded = await loadBookmarks();
    expect(loaded).toHaveLength(1);
    expect(loaded[0].id).toBe('b1');
  });

  it('saveBookmark prepends (newest first)', async () => {
    await saveBookmark(makeBookmark('b1'));
    await saveBookmark(makeBookmark('b2'));
    const loaded = await loadBookmarks();
    expect(loaded[0].id).toBe('b2');
  });

  it('saveBookmark caps at 100', async () => {
    for (let i = 0; i < 105; i++) {
      await saveBookmark(makeBookmark(`b${i}`));
    }
    expect(await loadBookmarks()).toHaveLength(100);
  });

  it('deleteBookmark removes by id', async () => {
    await saveBookmark(makeBookmark('b1'));
    await saveBookmark(makeBookmark('b2'));
    await deleteBookmark('b1');
    const loaded = await loadBookmarks();
    expect(loaded).toHaveLength(1);
    expect(loaded[0].id).toBe('b2');
  });
});

// ---- Server Config ----

describe('Server Config', () => {
  it('loadServerConfig returns defaults when empty', async () => {
    const cfg = await loadServerConfig();
    expect(cfg.url).toBe('http://localhost:8090');
    expect(cfg.apiKey).toBe('');
  });

  it('saveServerConfig persists and loads', async () => {
    await saveServerConfig('http://myserver:9000', 'key123');
    const cfg = await loadServerConfig();
    expect(cfg.url).toBe('http://myserver:9000');
    expect(cfg.apiKey).toBe('key123');
  });
});
