/**
 * Auth API — login + token persistence.
 */
import { api, setToken } from './client';

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export async function login(username: string, password: string): Promise<LoginResponse> {
  // FastAPI's OAuth2PasswordRequestForm expects form-urlencoded
  const formData = new URLSearchParams();
  formData.append('username', username);
  formData.append('password', password);

  const { data } = await api.post<LoginResponse>('/api/auth/login', formData.toString(), {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  });

  setToken(data.access_token);
  return data;
}

export function logout() {
  setToken(null);
}
