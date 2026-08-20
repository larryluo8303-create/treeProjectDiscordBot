import { useQuery, useMutation } from '@tanstack/react-query';
import { api } from './client';

// ---- Chat ----
export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  confidence?: number;
  sources?: Array<{ text: string; score: number; type: string }>;
  imageUrl?: string;
  timestamp: number;
}

interface ChatRequest {
  message: string;
  conversation_history?: Array<{ role: string; content: string }>;
}

interface ChatResponse {
  answer: string;
  confidence: number;
  sources: Array<{ text: string; score: number; type: string }>;
}

export function useSendMessage() {
  return useMutation({
    mutationFn: async (body: ChatRequest): Promise<ChatResponse> => {
      const resp = await api.post('/api/public/chat', body);
      return resp.data;
    },
  });
}

// ---- Vision ----
interface VisionResponse {
  answer: string;
  confidence: number;
}

export function useAnalyzeImage() {
  return useMutation({
    mutationFn: async (params: { file: File; text?: string }): Promise<VisionResponse> => {
      const formData = new FormData();
      formData.append('image', params.file);
      if (params.text) formData.append('text', params.text);
      const resp = await api.post('/api/public/analyze-image', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 60000,
      });
      return resp.data;
    },
  });
}

// ---- FAQ ----
export function useFAQ() {
  return useQuery({
    queryKey: ['public-faq'],
    queryFn: async () => {
      const resp = await api.get('/api/public/faq');
      return resp.data;
    },
    staleTime: 5 * 60 * 1000,
  });
}

// ---- KB Search ----
export function useKBSearch(query: string) {
  return useQuery({
    queryKey: ['public-kb-search', query],
    queryFn: async () => {
      const resp = await api.get('/api/public/kb/search', { params: { q: query, top_k: 8 } });
      return resp.data;
    },
    enabled: query.trim().length > 0,
    staleTime: 60 * 1000,
  });
}

// ---- Promos & Lessons ----
export function usePromos() {
  return useQuery({
    queryKey: ['public-promos'],
    queryFn: async () => (await api.get('/api/public/promos')).data,
    staleTime: 5 * 60 * 1000,
  });
}

export function useLessons() {
  return useQuery({
    queryKey: ['public-lessons'],
    queryFn: async () => (await api.get('/api/public/lessons')).data,
    staleTime: 5 * 60 * 1000,
  });
}

// ---- Digest ----
export function useDigest() {
  return useQuery({
    queryKey: ['public-digest'],
    queryFn: async () => (await api.get('/api/public/digest')).data,
    staleTime: 5 * 60 * 1000,
    refetchInterval: 5 * 60 * 1000,
  });
}

// ---- Market News ----
export interface NewsItem {
  id: string;
  time: string;
  important: boolean;
  title: string;
  body: string;
  pic: string | null;
  link: string | null;
}

export function useNews(limit = 50) {
  return useQuery({
    queryKey: ['public-news', limit],
    queryFn: async () => {
      const resp = await api.get('/api/public/news', { params: { limit } });
      return resp.data as { count: number; items: NewsItem[] };
    },
    staleTime: 15 * 1000,
    refetchInterval: 30 * 1000,
  });
}

// ---- Summaries (daily & weekly) ----
export interface SummaryItem {
  type: 'daily' | 'weekly';
  title: string;
  content: string;
  message_count: number;
  timestamp: string;
}

export function useSummaries(type?: 'daily' | 'weekly') {
  return useQuery({
    queryKey: ['public-summaries', type],
    queryFn: async () => {
      const params: Record<string, string | number> = { limit: 30 };
      if (type) params.type = type;
      const resp = await api.get('/api/public/summaries', { params });
      return resp.data as { count: number; items: SummaryItem[] };
    },
    staleTime: 5 * 60 * 1000,
    refetchInterval: 5 * 60 * 1000,
  });
}

// ---- Lesson Archive ----
export function useLessonArchive() {
  return useQuery({
    queryKey: ['public-lessons-archive'],
    queryFn: async () => (await api.get('/api/public/lessons/archive')).data,
    staleTime: 10 * 60 * 1000,
  });
}
