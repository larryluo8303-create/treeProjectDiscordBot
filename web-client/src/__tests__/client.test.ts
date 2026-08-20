import { describe, it, expect, beforeEach } from 'vitest';
import { api, setBaseURL, getBaseURL, setApiKey, getApiKey } from '../api/client';

beforeEach(() => {
  localStorage.clear();
  // Reset to defaults
  setBaseURL('');
  setApiKey('');
});

describe('API client', () => {
  it('has default baseURL', () => {
    expect(getBaseURL()).toBe('');
  });

  it('setBaseURL updates axios defaults and strips trailing slashes', () => {
    setBaseURL('http://example.com:9000///');
    expect(getBaseURL()).toBe('http://example.com:9000');
    expect(api.defaults.baseURL).toBe('http://example.com:9000');
  });

  it('setBaseURL persists to localStorage', () => {
    setBaseURL('http://my-server:8090');
    expect(localStorage.getItem('bigtree_server_url')).toBe('http://my-server:8090');
  });

  it('getApiKey returns empty string by default', () => {
    expect(getApiKey()).toBe('');
  });

  it('setApiKey sets the x-api-key header', () => {
    setApiKey('my-secret-key');
    expect(getApiKey()).toBe('my-secret-key');
    expect(api.defaults.headers.common['x-api-key']).toBe('my-secret-key');
  });

  it('setApiKey clears header when empty', () => {
    setApiKey('my-key');
    setApiKey('');
    expect(api.defaults.headers.common['x-api-key']).toBeUndefined();
  });

  it('setApiKey persists to localStorage', () => {
    setApiKey('persisted-key');
    expect(localStorage.getItem('bigtree_api_key')).toBe('persisted-key');
  });

  it('api instance has correct default timeout', () => {
    expect(api.defaults.timeout).toBe(30000);
  });

  it('api instance has JSON content type', () => {
    expect(api.defaults.headers['Content-Type']).toBe('application/json');
  });
});
