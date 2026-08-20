import { useMutation } from '@tanstack/react-query';
import { api } from './client';

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  confidence?: number;
  sources?: Array<{ text: string; score: number; type: string }>;
  imageUri?: string;
  timestamp: number;
}

interface ChatRequest {
  message: string;
  conversation_history?: Array<{ role: string; content: string }>;
}

interface ChatResponse {
  answer: string;
  confidence: number;
  sources: Array<{ text: string; score: number; type: string }>;
}

export function useSendMessage() {
  return useMutation({
    mutationFn: async (body: ChatRequest): Promise<ChatResponse> => {
      const resp = await api.post('/api/public/chat', body);
      return resp.data;
    },
  });
}
