/** Review queue API hooks. */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from './client';

export interface ReviewItem {
  id: string;
  channel_id: number;
  channel_name: string;
  message_id: number;
  author_name: string;
  author_id: number;
  question: string;
  draft_answer: string;
  confidence: number;
  context_snippets: Array<{ text?: string; distance?: number }>;
  created_at: number;
  status: 'pending' | 'approved' | 'edited' | 'rejected';
  final_answer: string;
  reviewed_at: number;
  jump_url: string;
}

export function usePendingReviews() {
  return useQuery<{ count: number; items: ReviewItem[] }>({
    queryKey: ['reviews', 'pending'],
    queryFn: async () => (await api.get('/api/review/pending')).data,
    refetchInterval: 15_000,
  });
}

export function useAllReviews(limit = 50) {
  return useQuery<{ count: number; items: ReviewItem[] }>({
    queryKey: ['reviews', 'all', limit],
    queryFn: async () => (await api.get(`/api/review/all?limit=${limit}`)).data,
  });
}

export function useApproveReview() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (itemId: string) => {
      const { data } = await api.post(`/api/review/${itemId}/approve`);
      return data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['reviews'] }),
  });
}

export function useEditReview() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ itemId, answer }: { itemId: string; answer: string }) => {
      const { data } = await api.post(`/api/review/${itemId}/edit`, { answer });
      return data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['reviews'] }),
  });
}

export function useRejectReview() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (itemId: string) => {
      const { data } = await api.post(`/api/review/${itemId}/reject`);
      return data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['reviews'] }),
  });
}
