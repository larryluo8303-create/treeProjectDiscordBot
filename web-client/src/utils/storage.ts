import type { ChatMessage } from '../api/hooks';

const CHAT_HISTORY_KEY = 'bigtree_chat_history';
const BOOKMARKS_KEY = 'bigtree_bookmarks';

// ---- Chat Sessions ----
export interface ChatSession {
  id: string;
  title: string;
  messages: ChatMessage[];
  createdAt: number;
  updatedAt: number;
}

export function loadSessions(): ChatSession[] {
  try {
    const raw = localStorage.getItem(CHAT_HISTORY_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveSessions(sessions: ChatSession[]) {
  localStorage.setItem(CHAT_HISTORY_KEY, JSON.stringify(sessions));
}

export function saveCurrentSession(session: ChatSession) {
  const sessions = loadSessions();
  const idx = sessions.findIndex((s) => s.id === session.id);
  if (idx >= 0) sessions[idx] = session;
  else sessions.unshift(session);
  saveSessions(sessions.slice(0, 50));
}

export function deleteSession(id: string) {
  saveSessions(loadSessions().filter((s) => s.id !== id));
}

// ---- Bookmarks ----
export interface Bookmark {
  id: string;
  question: string;
  answer: string;
  confidence: number;
  savedAt: number;
}

export function loadBookmarks(): Bookmark[] {
  try {
    const raw = localStorage.getItem(BOOKMARKS_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

export function saveBookmark(bookmark: Bookmark) {
  const bookmarks = loadBookmarks();
  bookmarks.unshift(bookmark);
  localStorage.setItem(BOOKMARKS_KEY, JSON.stringify(bookmarks.slice(0, 100)));
}

export function deleteBookmark(id: string) {
  const bookmarks = loadBookmarks().filter((b) => b.id !== id);
  localStorage.setItem(BOOKMARKS_KEY, JSON.stringify(bookmarks));
}
