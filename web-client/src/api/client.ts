import axios, { type AxiosInstance } from 'axios';

const STORAGE_URL_KEY = 'bigtree_server_url';
const STORAGE_API_KEY = 'bigtree_api_key';

let _baseURL = localStorage.getItem(STORAGE_URL_KEY) || '';
let _apiKey = localStorage.getItem(STORAGE_API_KEY) || '';

export const api: AxiosInstance = axios.create({
  baseURL: _baseURL,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

if (_apiKey) {
  api.defaults.headers.common['x-api-key'] = _apiKey;
}

export function setBaseURL(url: string) {
  _baseURL = url.replace(/\/+$/, '');
  api.defaults.baseURL = _baseURL;
  localStorage.setItem(STORAGE_URL_KEY, _baseURL);
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
  localStorage.setItem(STORAGE_API_KEY, key);
}

export function getApiKey(): string {
  return _apiKey;
}
