/** Config API hooks. */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from './client';

export interface BotConfig {
  respond_mode: string;
  confidence_threshold: number;
  llm_model: string;
  embedding_model: string;
  vision_model: string;
  target_channel_ids: number[];
  owner_user_id: number;
  user_cooldown_seconds: number;
  global_max_per_minute: number;
  conversation_memory_size: number;
  conversation_memory_ttl: number;
  thread_auto_reply: boolean;
  thread_context_messages: number;
}

export function useConfig() {
  return useQuery<BotConfig>({
    queryKey: ['config'],
    queryFn: async () => (await api.get('/api/config')).data,
  });
}

export function usePatchConfig() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (patch: Partial<BotConfig>) => {
      const { data } = await api.patch('/api/config', patch);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['config'] });
    },
  });
}
