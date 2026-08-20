import { useQuery } from '@tanstack/react-query';
import { api } from './client';

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
