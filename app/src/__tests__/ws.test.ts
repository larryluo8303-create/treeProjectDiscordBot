import { describe, it, expect, vi, beforeEach } from 'vitest';

// Track created mock WebSocket instances
const wsInstances: any[] = [];

vi.stubGlobal('WebSocket', class MockWebSocket {
  onopen: any = null;
  onmessage: any = null;
  onclose: any = null;
  onerror: any = null;
  close = vi.fn();
  send = vi.fn();
  constructor(public url: string) {
    wsInstances.push(this);
  }
});

// Mock the client module
let mockGetToken: () => string | null = () => 'test-token';
vi.mock('../api/client', () => ({
  getBaseURL: () => 'http://localhost:8090',
  getToken: () => mockGetToken(),
  setToken: vi.fn(),
}));

import { wsManager } from '../api/ws';

describe('WSManager', () => {
  beforeEach(() => {
    wsInstances.length = 0;
    mockGetToken = () => 'test-token';
    wsManager.disconnect();
  });

  it('connect creates a WebSocket with correct URL', () => {
    wsManager.connect();
    expect(wsInstances).toHaveLength(1);
    expect(wsInstances[0].url).toContain('ws://localhost:8090/api/ws?token=test-token');
  });

  it('onEvent registers handler and returns unsubscribe', () => {
    const handler = vi.fn();
    const unsub = wsManager.onEvent(handler);
    expect(typeof unsub).toBe('function');
    unsub();
  });

  it('disconnect closes WebSocket', () => {
    wsManager.connect();
    const ws = wsInstances[0];
    wsManager.disconnect();
    expect(ws.close).toHaveBeenCalled();
  });

  it('onEvent handler receives dispatched events', () => {
    const handler = vi.fn();
    wsManager.onEvent(handler);
    wsManager.connect();
    const ws = wsInstances[0];

    ws.onmessage({ data: JSON.stringify({ type: 'new_query' }) });

    expect(handler).toHaveBeenCalledWith({ type: 'new_query' });
  });

  it('ignores non-JSON messages', () => {
    const handler = vi.fn();
    wsManager.onEvent(handler);
    wsManager.connect();
    const ws = wsInstances[0];

    ws.onmessage({ data: 'not json' });

    expect(handler).not.toHaveBeenCalled();
  });

  it('unsubscribed handler stops receiving events', () => {
    const handler = vi.fn();
    const unsub = wsManager.onEvent(handler);
    wsManager.connect();
    const ws = wsInstances[0];

    unsub();

    ws.onmessage({ data: JSON.stringify({ type: 'test' }) });

    expect(handler).not.toHaveBeenCalled();
  });

  it('connect does nothing when no token', () => {
    mockGetToken = () => null;
    wsInstances.length = 0;
    wsManager.connect();
    expect(wsInstances).toHaveLength(0);
  });
});
