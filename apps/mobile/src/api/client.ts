import type { RequestOptions } from './types';

export class ApiError extends Error {
  constructor(message: string, public readonly status = 0, public readonly code?: string) { super(message); this.name = 'ApiError'; }
}
export function apiOrigin(raw: string | undefined, development: boolean): string {
  if (!raw) throw new ApiError('This app needs a connection to your Shiftly service. Ask your administrator to configure it.');
  let url: URL;
  try { url = new URL(raw); } catch { throw new ApiError('The Shiftly service address is invalid.'); }
  const host = url.hostname;
  const parts = host.split('.');
  const ipv4 = parts.length === 4 && parts.every(p => /^\d{1,3}$/.test(p) && Number(p) <= 255);
  const first = Number(parts[0]), second = Number(parts[1]);
  const local = host === 'localhost' || host === '[::1]' || (ipv4 && (first === 127 || first === 10
    || (first === 192 && second === 168) || (first === 172 && second >= 16 && second <= 31)));
  if (url.username || url.password || url.search || url.hash || url.pathname !== '/'
      || (url.protocol !== 'https:' && !(development && local && url.protocol === 'http:'))) {
    throw new ApiError('Use a secure Shiftly service address. Local HTTP is available only during development.');
  }
  return url.origin;
}
export interface Transport { send<T>(path: string, options?: RequestOptions, token?: string): Promise<T> }
export function createTransport(origin: string, fetcher: typeof fetch = fetch): Transport {
  return {
    async send<T>(path: string, options: RequestOptions = {}, token?: string): Promise<T> {
      // Feature paths stay under the fixed mobile API. No traversal, encoded
      // separators, URL/query injection, or already-prefixed API paths.
      if (path.length > 2048 || path.trim() !== path || !/^\/(?!api(?:\/|$))[a-z][a-z0-9-]*(?:\/[A-Za-z0-9_-]+)*$/.test(path)) {
        throw new ApiError('This action is not available.');
      }
      const abort = new AbortController();
      const timer = setTimeout(() => abort.abort(), 20_000);
      try {
        const query = options.query ? `?${new URLSearchParams(options.query).toString()}` : '';
        const response = await fetcher(`${origin}/api/mobile${path}${query}`, {
          method: options.method ?? 'GET',
          headers: { Accept: 'application/json', ...(options.body ? { 'Content-Type': 'application/json' } : {}),
            ...(token ? { Authorization: `Bearer ${token}` } : {}) },
          body: options.body ? JSON.stringify(options.body) : undefined,
          credentials: 'omit', redirect: 'error', signal: abort.signal,
        });
        let value: unknown;
        try { value = await response.json(); } catch { throw new ApiError('The service returned an unreadable response.', response.status); }
        if (!response.ok) {
          const message = value && typeof value === 'object' && 'error' in value && typeof value.error === 'string'
            ? value.error : 'The request could not be completed.';
          const code = value && typeof value === 'object' && 'errorCode' in value && typeof value.errorCode === 'string'
            ? value.errorCode : undefined;
          throw new ApiError(message, response.status, code);
        }
        return value as T;
      } catch (error) {
        if (error instanceof ApiError) throw error;
        if (options.method === 'POST') {
          throw new ApiError(options.uncertainMessage || "We couldn't confirm this change. Refresh the affected screen or sign in again to check the result before trying again.");
        }
        throw new ApiError('Could not reach Shiftly. Check your connection and try again.');
      } finally { clearTimeout(timer); }
    },
  };
}
