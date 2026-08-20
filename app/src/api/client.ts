/**
 * Axios-based API client with JWT auth header injection.
 */
import axios, { type AxiosInstance } from 'axios';

// Default to localhost for dev; override via environment or settings screen
let _baseURL = 'http://localhost:8090';
let _token: string | null = null;

export function setBaseURL(url: string) {
  _baseURL = url.replace(/\/+$/, '');
  api.defaults.baseURL = _baseURL;
}

export function getBaseURL(): string {
  return _baseURL;
}

export function setToken(token: string | null) {
  _token = token;
  if (token) {
    api.defaults.headers.common['Authorization'] = `Bearer ${token}`;
  } else {
    delete api.defaults.headers.common['Authorization'];
  }
}

export function getToken(): string | null {
  return _token;
}

export const api: AxiosInstance = axios.create({
  baseURL: _baseURL,
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Response interceptor for 401 handling
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Token expired — clear it so the app redirects to login
      setToken(null);
    }
    return Promise.reject(error);
  },
);
