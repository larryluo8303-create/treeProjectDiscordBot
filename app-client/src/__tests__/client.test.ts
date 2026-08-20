import { describe, it, expect, beforeEach } from 'vitest';
import { api, setBaseURL, getBaseURL, setApiKey, getApiKey } from '../api/client';

describe('API client', () => {
  beforeEach(() => {
    setBaseURL('http://localhost:8090');
    setApiKey('');
  });

  it('has default baseURL', () => {
    expect(getBaseURL()).toBe('http://localhost:8090');
  });

  it('setBaseURL updates axios defaults and strips trailing slashes', () => {
    setBaseURL('http://example.com:9000///');
    expect(getBaseURL()).toBe('http://example.com:9000');
    expect(api.defaults.baseURL).toBe('http://example.com:9000');
  });

  it('getApiKey returns empty string by default', () => {
    expect(getApiKey()).toBe('');
  });

  it('setApiKey sets the x-api-key header', () => {
    setApiKey('my-secret');
    expect(getApiKey()).toBe('my-secret');
    expect(api.defaults.headers.common['x-api-key']).toBe('my-secret');
  });

  it('setApiKey clears header when empty', () => {
    setApiKey('temp');
    setApiKey('');
    expect(api.defaults.headers.common['x-api-key']).toBeUndefined();
  });

  it('api instance has correct timeout', () => {
    expect(api.defaults.timeout).toBe(30000);
  });

  it('api instance has JSON content type', () => {
    expect(api.defaults.headers['Content-Type']).toBe('application/json');
  });
});
