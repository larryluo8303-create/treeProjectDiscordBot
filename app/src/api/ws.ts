/**
 * WebSocket manager — connects to the API server and dispatches events
 * to invalidate TanStack Query caches for real-time updates.
 */
import { QueryClient } from '@tanstack/react-query';
import { getBaseURL, getToken } from './client';

type EventHandler = (event: WSEvent) => void;

export interface WSEvent {
  type: string;
  [key: string]: unknown;
}

class WSManager {
  private ws: WebSocket | null = null;
  private handlers: EventHandler[] = [];
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private queryClient: QueryClient | null = null;

  setQueryClient(qc: QueryClient) {
    this.queryClient = qc;
  }

  connect() {
    const token = getToken();
    if (!token) return;

    const baseUrl = getBaseURL().replace(/^http/, 'ws');
    const url = `${baseUrl}/api/ws?token=${encodeURIComponent(token)}`;

    try {
      this.ws = new WebSocket(url);

      this.ws.onopen = () => {
        console.log('[WS] Connected');
      };

      this.ws.onmessage = (event) => {
        try {
          const data: WSEvent = JSON.parse(event.data);
          this._dispatch(data);
        } catch {
          // ignore non-JSON messages
        }
      };

      this.ws.onclose = () => {
        console.log('[WS] Disconnected — reconnecting in 5s');
        this._scheduleReconnect();
      };

      this.ws.onerror = () => {
        this.ws?.close();
      };
    } catch {
      this._scheduleReconnect();
    }
  }

  disconnect() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.onclose = null;
      this.ws.close();
      this.ws = null;
    }
  }

  onEvent(handler: EventHandler) {
    this.handlers.push(handler);
    return () => {
      this.handlers = this.handlers.filter((h) => h !== handler);
    };
  }

  private _dispatch(event: WSEvent) {
    // Auto-invalidate relevant queries based on event type
    if (this.queryClient) {
      switch (event.type) {
        case 'review_request':
        case 'review_resolved':
          this.queryClient.invalidateQueries({ queryKey: ['reviews'] });
          break;
        case 'config_changed':
          this.queryClient.invalidateQueries({ queryKey: ['config'] });
          break;
        case 'new_query':
          this.queryClient.invalidateQueries({ queryKey: ['stats'] });
          break;
      }
    }
    // Forward to custom handlers
    for (const handler of this.handlers) {
      try {
        handler(event);
      } catch {
        // swallow handler errors
      }
    }
  }

  private _scheduleReconnect() {
    if (this.reconnectTimer) return;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, 5000);
  }
}

export const wsManager = new WSManager();
