import axios from 'axios';

export const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';

const TOKEN_KEY = 'auth_token';

export function getToken(): string | null {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}

export function setToken(token: string): void {
  try { localStorage.setItem(TOKEN_KEY, token); } catch { /* quota */ }
}

export function clearToken(): void {
  try { localStorage.removeItem(TOKEN_KEY); } catch { /* quota */ }
}

export const api = axios.create({ baseURL: `${API_BASE}/v1` });

api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

/** Build a stream URL, appending ?token= for EventSource (can't send headers). */
export function streamUrl(path: string): string {
  const token = getToken();
  if (!token) return `${API_BASE}/v1${path}`;
  const url = new URL(`${API_BASE}/v1${path}`);
  url.searchParams.set('token', token);
  return url.toString();
}
