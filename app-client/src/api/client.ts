import axios, { type AxiosInstance } from 'axios';
import AsyncStorage from '@react-native-async-storage/async-storage';

const STORAGE_URL_KEY = 'bigtree_server_url';
const STORAGE_API_KEY = 'bigtree_api_key';

let _baseURL = 'http://localhost:8090';
let _apiKey = '';
let _initialized = false;

export const api: AxiosInstance = axios.create({
  baseURL: _baseURL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

/**
 * Load persisted server URL and API key from AsyncStorage.
 * Call once at app startup (e.g. in the root layout).
 */
export async function initClient(): Promise<void> {
  if (_initialized) return;
  try {
    const savedUrl = await AsyncStorage.getItem(STORAGE_URL_KEY);
    const savedKey = await AsyncStorage.getItem(STORAGE_API_KEY);
    if (savedUrl) setBaseURL(savedUrl);
    if (savedKey) setApiKey(savedKey);
  } catch {
    // ignore — use defaults
  }
  _initialized = true;
}

export function setBaseURL(url: string) {
  _baseURL = url.replace(/\/+$/, '');
  api.defaults.baseURL = _baseURL;
}

export function getBaseURL(): string {
  return _baseURL;
}

export function setApiKey(key: string) {
  _apiKey = key;
  if (key) {
    api.defaults.headers.common['x-api-key'] = key;
  } else {
    delete api.defaults.headers.common['x-api-key'];
  }
}

export function getApiKey(): string {
  return _apiKey;
}
