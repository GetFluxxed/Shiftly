/// <reference types="node" />
import assert from 'node:assert/strict';
import test from 'node:test';
import { ApiError, apiOrigin, createTransport } from '../src/api/client';

const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), {
  status, headers: { 'Content-Type': 'application/json' },
});

test('release service configuration accepts only HTTPS origins without embedded data', () => {
  assert.equal(apiOrigin('https://shiftly.example:8443/', false), 'https://shiftly.example:8443');
  for (const value of [undefined, '', 'not a URL', 'http://127.0.0.1:4174', 'ftp://shiftly.example',
    'https://person:password@shiftly.example', 'https://shiftly.example/api/mobile',
    'https://shiftly.example/?token=private', 'https://shiftly.example/#private']) {
    assert.throws(() => apiOrigin(value, false), ApiError, value);
  }
});

test('development HTTP is restricted to actual loopback or private IPv4 hosts', () => {
  for (const host of ['localhost', '[::1]', '127.0.0.1', '10.0.2.2', '192.168.1.14', '172.16.0.1', '172.31.255.254']) {
    assert.equal(apiOrigin(`http://${host}:4174`, true), `http://${host}:4174`);
  }
  for (const host of ['shiftly.example', '8.8.8.8', '172.15.0.1', '172.32.0.1',
    '10.attacker.example', '127.attacker.example', '192.168.attacker.example', '172.16.attacker.example']) {
    assert.throws(() => apiOrigin(`http://${host}:4174`, true), ApiError, host);
  }
});

test('native requests send an explicit bearer and JSON, omit cookies, and reject redirects', async () => {
  let captured: { input: string; init?: RequestInit } | undefined;
  const fetcher = (async (input: string | URL | Request, init?: RequestInit) => {
    captured = { input: String(input), init }; return json({ ok: true });
  }) as typeof fetch;
  const api = createTransport('https://shiftly.example', fetcher);
  assert.deepEqual(await api.send('/reports', { method: 'POST', body: { notes: 'Useful shift detail', expectedStoreId: 7 } }, 'opaque-session'), { ok: true });
  assert.equal(captured?.input, 'https://shiftly.example/api/mobile/reports');
  assert.equal(captured?.init?.credentials, 'omit');
  assert.equal(captured?.init?.redirect, 'error');
  assert.equal(captured?.init?.method, 'POST');
  assert.deepEqual(captured?.init?.headers, {
    Accept: 'application/json', 'Content-Type': 'application/json', Authorization: 'Bearer opaque-session',
  });
  assert.deepEqual(JSON.parse(String(captured?.init?.body)), { notes: 'Useful shift detail', expectedStoreId: 7 });
  assert.ok(captured?.init?.signal instanceof AbortSignal);
});

test('public account requests never invent an authentication header', async () => {
  let headers: HeadersInit | undefined;
  const api = createTransport('https://shiftly.example', (async (_url, init) => {
    headers = init?.headers; return json({ authenticated: false });
  }) as typeof fetch);
  await api.send('/accounts/status');
  assert.deepEqual(headers, { Accept: 'application/json' });
});

test('path validation prevents moving credentials outside the fixed mobile API', async () => {
  let requests = 0;
  const api = createTransport('https://shiftly.example', (async () => { requests++; return json({}); }) as typeof fetch);
  for (const path of ['https://attacker.example/accounts/status', '//attacker.example', '/accounts/../status',
    '/reports?token=x', '/reports#fragment', '/api/accounts/status', '/accounts/status/../../reports']) {
    await assert.rejects(api.send(path, {}, 'private-token'), ApiError);
  }
  assert.equal(requests, 0);
});

test('safe server errors preserve authentication status for session invalidation', async () => {
  const api = createTransport('https://shiftly.example', (async () => json({ error: 'Session has expired.' }, 401)) as typeof fetch);
  await assert.rejects(api.send('/accounts/status'), error => error instanceof ApiError
    && error.status === 401 && error.message === 'Session has expired.');
});

test('non-JSON errors retain status and hide raw response content', async () => {
  const api = createTransport('https://shiftly.example', (async () => new Response('private traceback', { status: 503 })) as typeof fetch);
  await assert.rejects(api.send('/accounts/status'), error => error instanceof ApiError
    && error.status === 503 && !error.message.includes('private traceback'));
});

test('network failures expose a safe message and never retry writes automatically', async () => {
  let calls = 0;
  const api = createTransport('https://shiftly.example', (async () => {
    calls++; throw new Error('private-token private-network-details');
  }) as typeof fetch);
  await assert.rejects(api.send('/reports', { method: 'POST', body: { notes: 'private report' } }, 'private-token'),
    error => error instanceof ApiError && error.status === 0 && !error.message.includes('private-')
      && error.message.includes('may have been saved') && error.message.includes('before sending it again'));
  assert.equal(calls, 1);
});
