import AsyncStorage from '@react-native-async-storage/async-storage';
import type { ChatMessage } from '../api/chat';

const CHAT_HISTORY_KEY = 'bigtree_chat_history';
const BOOKMARKS_KEY = 'bigtree_bookmarks';
const SERVER_URL_KEY = 'bigtree_server_url';
const API_KEY_KEY = 'bigtree_api_key';

// ---------------------------------------------------------------------------
// Chat History
// ---------------------------------------------------------------------------
export interface ChatSession {
  id: string;
  title: string;
  messages: ChatMessage[];
  createdAt: number;
  updatedAt: number;
}

export async function loadSessions(): Promise<ChatSession[]> {
  try {
    const raw = await AsyncStorage.getItem(CHAT_HISTORY_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

export async function saveSessions(sessions: ChatSession[]): Promise<void> {
  await AsyncStorage.setItem(CHAT_HISTORY_KEY, JSON.stringify(sessions));
}

export async function saveCurrentSession(session: ChatSession): Promise<void> {
  const sessions = await loadSessions();
  const idx = sessions.findIndex((s: ChatSession) => s.id === session.id);
  if (idx >= 0) {
    sessions[idx] = session;
  } else {
    sessions.unshift(session);
  }
  // Keep last 50 sessions
  await saveSessions(sessions.slice(0, 50));
}

export async function deleteSession(id: string): Promise<void> {
  const sessions = await loadSessions();
  await saveSessions(sessions.filter((s: ChatSession) => s.id !== id));
}

// ---------------------------------------------------------------------------
// Bookmarks
// ---------------------------------------------------------------------------
export interface Bookmark {
  id: string;
  question: string;
  answer: string;
  confidence: number;
  savedAt: number;
}

export async function loadBookmarks(): Promise<Bookmark[]> {
  try {
    const raw = await AsyncStorage.getItem(BOOKMARKS_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

export async function saveBookmark(bookmark: Bookmark): Promise<void> {
  const bookmarks = await loadBookmarks();
  bookmarks.unshift(bookmark);
  // Keep last 100 bookmarks
  await AsyncStorage.setItem(BOOKMARKS_KEY, JSON.stringify(bookmarks.slice(0, 100)));
}

export async function deleteBookmark(id: string): Promise<void> {
  const bookmarks = await loadBookmarks();
  await AsyncStorage.setItem(
    BOOKMARKS_KEY,
    JSON.stringify(bookmarks.filter((b: Bookmark) => b.id !== id))
  );
}

// ---------------------------------------------------------------------------
// Server config persistence
// ---------------------------------------------------------------------------
export async function loadServerConfig(): Promise<{ url: string; apiKey: string }> {
  try {
    const url = (await AsyncStorage.getItem(SERVER_URL_KEY)) || 'http://localhost:8090';
    const apiKey = (await AsyncStorage.getItem(API_KEY_KEY)) || '';
    return { url, apiKey };
  } catch {
    return { url: 'http://localhost:8090', apiKey: '' };
  }
}

export async function saveServerConfig(url: string, apiKey: string): Promise<void> {
  await AsyncStorage.setItem(SERVER_URL_KEY, url);
  await AsyncStorage.setItem(API_KEY_KEY, apiKey);
}
