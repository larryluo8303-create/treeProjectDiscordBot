/** Stats API hooks. */
import { useQuery } from '@tanstack/react-query';
import { api } from './client';

export interface StatsSnapshot {
  total_queries: number;
  auto_replies: number;
  forwards: number;
  avg_confidence: number;
  avg_latency_ms: number;
  uptime_seconds: number;
  recent: Array<{
    question: string;
    channel_id: number;
    confidence: number;
    action: string;
    latency_ms: number;
    timestamp: number;
  }>;
}

export function useStats() {
  return useQuery<StatsSnapshot>({
    queryKey: ['stats'],
    queryFn: async () => (await api.get('/api/stats')).data,
    refetchInterval: 10_000,
  });
}
