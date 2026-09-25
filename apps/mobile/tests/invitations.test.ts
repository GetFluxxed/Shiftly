import assert from 'node:assert/strict';
import test from 'node:test';
import { invitationLink, invitationToken } from '../src/accounts/invitations';
const secret = 'a'.repeat(43);
test('invitation links keep secrets out of requests and carry no permissions', () => {
  for (const base of ['shiftly://activate', 'exp://192.168.1.2:8081/--/activate', 'https://shiftly.example/activate.html']) {
    const link = new URL(invitationLink(base, secret));
    assert.equal(link.search, '');
    assert.equal(invitationToken(link.hash), secret);
    assert.equal([...new URLSearchParams(link.hash.slice(1)).keys()].join(','), 'invitation');
  }
});
test('malformed, oversized and duplicated secrets cannot preload an activation', () => {
  for (const value of [undefined, ['invitation=x'], 'invitation=x', 'invitation=' + 'x'.repeat(700), `invitation=${secret}&invitation=${secret}`]) {
    assert.equal(invitationToken(value), '');
  }
});
