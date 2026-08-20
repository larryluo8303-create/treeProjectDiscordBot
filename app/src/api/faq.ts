/** FAQ API hooks. */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from './client';

export function useFAQ() {
  return useQuery<{ items: Array<{ question: string; answer: string }> }>({
    queryKey: ['faq'],
    queryFn: async () => (await api.get('/api/faq')).data,
  });
}

export function useGenerateFAQ() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const { data } = await api.post('/api/faq/generate');
      return data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['faq'] }),
  });
}
