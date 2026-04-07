import axios from 'axios';

export const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';
const API_KEY = import.meta.env.VITE_API_KEY as string | undefined;

export const api = axios.create({
  baseURL: API_BASE,
  headers: API_KEY ? { 'X-API-Key': API_KEY } : {},
});

/** Build a stream URL, appending ?api_key= when set (EventSource can't send headers). */
export function streamUrl(path: string): string {
  if (!API_KEY) return `${API_BASE}${path}`;
  const url = new URL(`${API_BASE}${path}`);
  url.searchParams.set('api_key', API_KEY);
  return url.toString();
}
