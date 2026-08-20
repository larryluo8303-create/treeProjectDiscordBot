import { useQuery } from '@tanstack/react-query';
import { api } from './client';

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
