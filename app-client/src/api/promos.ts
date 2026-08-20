import { useQuery } from '@tanstack/react-query';
import { api } from './client';

export function usePromos() {
  return useQuery({
    queryKey: ['public-promos'],
    queryFn: async () => {
      const resp = await api.get('/api/public/promos');
      return resp.data;
    },
    staleTime: 5 * 60 * 1000,
  });
}

export function useLessons() {
  return useQuery({
    queryKey: ['public-lessons'],
    queryFn: async () => {
      const resp = await api.get('/api/public/lessons');
      return resp.data;
    },
    staleTime: 5 * 60 * 1000,
  });
}
