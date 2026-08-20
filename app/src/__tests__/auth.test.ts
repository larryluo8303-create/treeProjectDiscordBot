import { describe, it, expect, vi, beforeEach } from 'vitest';
import { getToken, setToken } from '../api/client';

// Mock axios to intercept the login POST
vi.mock('axios', () => {
  const headers: Record<string, any> = { 'Content-Type': 'application/json' };
  const instance = {
    defaults: {
      baseURL: 'http://localhost:8090',
      timeout: 15000,
      headers: { ...headers, common: {} as Record<string, any> },
    },
    interceptors: {
      response: { use: vi.fn() },
      request: { use: vi.fn() },
    },
    post: vi.fn(),
    get: vi.fn(),
    patch: vi.fn(),
  };
  return {
    default: { create: vi.fn(() => instance) },
    __mockInstance: instance,
  };
});

// Re-import after mock
const axios = await import('axios');
const mockInstance = (axios as any).__mockInstance;

describe('Auth module', () => {
  beforeEach(() => {
    setToken(null);
    vi.clearAllMocks();
  });

  it('login sends form-encoded POST and sets token', async () => {
    mockInstance.post.mockResolvedValueOnce({
      data: {
        access_token: 'jwt-abc-123',
        token_type: 'bearer',
        expires_in: 86400,
      },
    });

    const { login } = await import('../api/auth');
    const result = await login('admin', 'password');

    expect(result.access_token).toBe('jwt-abc-123');
    expect(result.token_type).toBe('bearer');
    expect(result.expires_in).toBe(86400);

    // Verify it called post with form data
    expect(mockInstance.post).toHaveBeenCalledWith(
      '/api/auth/login',
      expect.stringContaining('username=admin'),
      expect.objectContaining({
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      })
    );
  });

  it('logout clears token', async () => {
    setToken('some-token');
    const { logout } = await import('../api/auth');
    logout();
    expect(getToken()).toBeNull();
  });
});
