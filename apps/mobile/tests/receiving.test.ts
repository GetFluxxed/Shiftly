import assert from 'node:assert/strict';
import test from 'node:test';
import { MutationIdentity } from '../src/inventory/api';
import type { Request } from '../src/inventory/api';
import type { RequestOptions } from '../src/api/types';
import { receivingApi, type Invoice, type InvoiceLineInput } from '../src/inventory/receiving/api';
import { WorkspaceController } from '../src/restoration/controller';
import type { CheckpointStorage } from '../src/restoration/storage';
import type { Snapshot } from '../src/session/controller';

const invoiceId = '11111111-1111-4111-8111-111111111111';
const productId = '22222222-2222-4222-8222-222222222222';
const lineId = '33333333-3333-4333-8333-333333333333';
const invoice = { id: invoiceId, storeId: 7, supplier: 'Dairy Co', invoiceNumber: '00042', state: 'draft', version: 1, lineCount: 1, receivedCount: 0, updatedAt: '2026-10-25T10:00:00Z', createdAt: '2026-10-25T09:00:00Z', baselineCountId: null, needsCountReview: false, needsCatalogReview: false, lines: [{ id: lineId, description: 'Milk', sku: 'MILK-01', productId, packageId: null, quantity: '2.500', unit: 'kg', received: false, productName: 'Milk', baseUnit: 'kg', normalizedQuantity: '2.500', packageName: null, needsCatalogReview: false }] };
const reply = (value: unknown): Request => async <T,>() => value as T;

test('invoice reads preserve exact decimal strings and leading-zero identifiers', async () => {
  const api = receivingApi(reply(invoice));
  const result = await api.invoice(invoiceId);
  assert.equal(result.invoiceNumber, '00042');
  assert.equal(result.lines[0]?.quantity, '2.500');
  assert.equal(result.lines[0]?.normalizedQuantity, '2.500');
  assert.equal(result.photoReadingAvailable, false);
});

test('unchanged invoice retry reuses its request identity and carries selected store and version', async () => {
  const bodies: Record<string, unknown>[] = [];
  const request: Request = async <T,>(_path: string, options?: RequestOptions) => { bodies.push(options?.body || {}); return { ...invoice, version: 2 } as T; };
  const api = receivingApi(request);
  const identity = new MutationIdentity();
  const fields: { supplier: string; invoiceNumber: string; lines: InvoiceLineInput[] } = { supplier: 'Dairy Co', invoiceNumber: '00042', lines: invoice.lines.map(({ productName: _p, baseUnit: _b, normalizedQuantity: _n, packageName: _k, ...line }) => ({ ...line, unit: 'kg' })) };
  await api.save({ ...invoice, version: 2 } as Invoice, fields, identity, 1); await api.save({ ...invoice, version: 2 } as Invoice, fields, identity, 1);
  assert.equal(bodies[0]?.requestId, bodies[1]?.requestId);
  assert.equal(bodies[0]?.expectedStoreId, 7);
  assert.equal(bodies[0]?.version, 1);
});

test('incoming unknown current remains null and malformed numeric values fail closed', async () => {
  const response = { items: [{ productId, name: 'Milk', baseUnit: 'kg', currentQuantity: null, incomingQuantity: '2.500', receivedQuantity: '0', projectedQuantity: null }], nextCursor: null, unmatchedCount: 1, needsCountReview: true, needsCatalogReview: false };
  const result = await receivingApi(reply(response)).incoming();
  assert.equal(result.items[0]?.currentQuantity, null); assert.equal(result.items[0]?.projectedQuantity, null);
  await assert.rejects(() => receivingApi(reply({ ...response, items: [{ ...response.items[0], incomingQuantity: 2.5 }] })).incoming(), /could not be verified/i);
});

test('photo analysis remains a proposal and rejects more than sixty lines', async () => {
  const proposal = { id: invoiceId, state: 'ready', canRetry: false, message: null, supplier: 'Dairy Co', invoiceNumber: '00042', lines: [{ description: 'Milk', sku: 'MILK-01', quantity: '2.500', unit: 'kg', productId, packageId: null }] };
  const api = receivingApi(reply(proposal));
  assert.equal((await api.photoAnalysis(invoiceId)).lines[0]?.quantity, '2.500');
  await assert.rejects(() => receivingApi(reply({ ...proposal, lines: Array(61).fill(proposal.lines[0]) })).photoAnalysis(invoiceId), /could not be verified/i);
});

test('a sixty-line invoice draft and pending request identity survive a real workspace checkpoint', async () => {
  const storage: CheckpointStorage & { value: string | null } = { value: null, async read() { return this.value; }, async write(value) { this.value = value; }, async remove() { this.value = null; } };
  const person = { userId: 1, businessId: 2, storeId: 7, username: 'owner', displayName: 'Owner', role: 'owner' as const, provenance: 'named' as const, capabilities: ['inventory.view'] };
  const session: Snapshot = { status: 'ready', actor: person, stores: [{ ...person, storeName: 'Store' }], message: null, busy: false, revision: 1 };
  const first = new WorkspaceController(storage, () => 2_000_000_000_000); first.accept(session);
  await new Promise<void>(resolve => setImmediate(resolve)); await new Promise<void>(resolve => setImmediate(resolve));
  const requestId = '77777777-7777-4777-8777-777777777777';
  const lines = Array.from({ length: 60 }, (_, index) => ({ id: `${String(index + 1).padStart(8, '0')}-1111-4111-8111-111111111111`, description: 'D'.repeat(160), sku: 'S'.repeat(64), productId, packageId: null, quantity: '123456789012345.123456789', unit: 'kg', received: false }));
  const draft = { baseVersion: 1, supplier: 'S'.repeat(120), invoiceNumber: 'I'.repeat(80), lines, mutation: { requestId } };
  first.write(`receiving.invoice.${invoiceId}`, draft, invoiceId, first.getSnapshot().scope); assert.equal(await first.flush(), true);
  assert.ok(storage.value && storage.value.length < 60_000); assert.ok(JSON.stringify(draft).length < 40_000); assert.equal(storage.value.includes('imageBase64'), false);
  const restarted = new WorkspaceController(storage, () => 2_000_000_000_000); restarted.accept(session);
  await new Promise<void>(resolve => setImmediate(resolve)); await new Promise<void>(resolve => setImmediate(resolve));
  assert.deepEqual(restarted.read(`receiving.invoice.${invoiceId}`, null, invoiceId, (_value): _value is typeof draft => true), draft);
});
