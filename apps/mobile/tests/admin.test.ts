import assert from 'node:assert/strict';
import test from 'node:test';
import { accountId, roleGrants } from '../src/accounts/types';

test('an account ID cannot silently round, accept scientific notation, or become zero', () => {
  for (const value of ['', '0', '-1', '1.2', '1e3', '9007199254740993', ' 12']) assert.equal(accountId(value), null);
  assert.equal(accountId('12'), 12);
});
test('changing a role preserves only grants offered by server policy, including stored role defaults', () => {
  assert.deepEqual(roleGrants({ role: 'crew', included: ['reports.submit'], optional: ['inventory.view'] },
    ['reports.submit', 'inventory.view', 'memberships.manage']), ['reports.submit', 'inventory.view']);
  assert.deepEqual(roleGrants(undefined, ['catalog.manage']), []);
});
