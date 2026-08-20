import { useQuery } from '@tanstack/react-query';
import { api } from './client';

export function useDigest() {
  return useQuery({
    queryKey: ['public-digest'],
    queryFn: async () => {
      const resp = await api.get('/api/public/digest');
      return resp.data;
    },
    staleTime: 5 * 60 * 1000,
    refetchInterval: 5 * 60 * 1000,
  });
}
