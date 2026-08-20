import { useQuery } from '@tanstack/react-query';
import { api } from './client';

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
