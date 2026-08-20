/** Knowledge base API hooks. */
import { useQuery } from '@tanstack/react-query';
import { api } from './client';

export interface KBInfo {
  count: number;
  samples: Array<{ id: string; type: string; text: string }>;
}

export interface KBSearchResult {
  query: string;
  count: number;
  results: Array<{
    text: string;
    distance: number;
    metadata: Record<string, string>;
  }>;
}

export function useKBInfo() {
  return useQuery<KBInfo>({
    queryKey: ['kb', 'info'],
    queryFn: async () => (await api.get('/api/kb')).data,
  });
}

export function useKBSearch(query: string, topK = 5) {
  return useQuery<KBSearchResult>({
    queryKey: ['kb', 'search', query, topK],
    queryFn: async () =>
      (await api.get('/api/kb/search', { params: { q: query, top_k: topK } })).data,
    enabled: query.length > 0,
  });
}
