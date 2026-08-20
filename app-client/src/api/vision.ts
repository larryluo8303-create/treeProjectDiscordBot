import { useMutation } from '@tanstack/react-query';
import { api } from './client';

interface VisionResponse {
  answer: string;
  confidence: number;
}

export function useAnalyzeImage() {
  return useMutation({
    mutationFn: async (params: { imageUri: string; text?: string }): Promise<VisionResponse> => {
      const formData = new FormData();

      // React Native / Expo file upload format
      const uriParts = params.imageUri.split('.');
      const ext = uriParts[uriParts.length - 1];
      formData.append('image', {
        uri: params.imageUri,
        name: `chart.${ext}`,
        type: `image/${ext === 'jpg' ? 'jpeg' : ext}`,
      } as any);

      if (params.text) {
        formData.append('text', params.text);
      }

      const resp = await api.post('/api/public/analyze-image', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 60000, // vision can be slow
      });
      return resp.data;
    },
  });
}
