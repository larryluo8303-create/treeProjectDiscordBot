import { useQuery } from '@tanstack/react-query';
import { api } from './client';

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
