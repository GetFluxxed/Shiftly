import assert from 'node:assert/strict';
import test from 'node:test';
import { inventoryApi, MutationIdentity } from '../src/inventory/api';
import { ApiError, createTransport } from '../src/api/client';
import type { RequestOptions } from '../src/api/types';
const product = { id:'11111111-1111-4111-8111-111111111111', name:'Milk', sku:'0001', baseUnit:'kg' as const, active:true, version:1, containerAmount:'6' };

test('same unchanged write retains its request ID, while edited content gets another ID', () => {
  const key = new MutationIdentity(); const a=key.for('/inventory/products',{name:'Milk',sku:'0001'});
  assert.equal(a,key.for('/inventory/products',{name:'Milk',sku:'0001'}));
  assert.notEqual(a,key.for('/inventory/products',{name:'Milk',sku:'0002'}));
  assert.match(a,/^[0-9a-f-]{36}$/);
});
test('product API preserves SKU text and sends versioned edits with no mutable unit', async () => {
  let call: {path:string;options?:RequestOptions} | undefined;
  const api=inventoryApi(async <T>(path:string, options?:RequestOptions) => {call={path,options};return product as T;});
  await api.createProduct({name:'Milk',sku:'0001',baseUnit:'kg',containerAmount:'6'},new MutationIdentity());
  assert.equal(call?.options?.body?.sku,'0001'); assert.equal(call?.options?.body?.baseUnit,'kg');
  await api.editProduct(product,'Milk','0002',new MutationIdentity());
  assert.equal(call?.options?.body?.containerAmount,'6');
  assert.equal(call?.options?.body?.version,1); assert.equal(call?.options?.body?.baseUnit,undefined);
  assert.ok(call?.options?.uncertainMessage);
});
test('inventory rejects malformed responses instead of letting unverified rows into screens', async () => {
  for(const row of [{...product,id:'../accounts'}, {...product,baseUnit:'invalid'}, {...product,version:0}]) {
    const api=inventoryApi(async <T>() => ({items:[row],nextCursor:null}) as T);
    await assert.rejects(api.products(),ApiError);
  }
});
test('search is encoded as query data and cannot move credentials outside the fixed API', async () => {
  let url=''; const transport=createTransport('https://shiftly.example',async input => {
    url=String(input);return new Response(JSON.stringify({items:[],nextCursor:null}),{status:200});
  });
  const api=inventoryApi(transport.send);
  await api.products('0001 & next=https://example.test/#?');
  const parsed=new URL(url);
  assert.equal(parsed.origin,'https://shiftly.example'); assert.equal(parsed.pathname,'/api/mobile/inventory/products');
  assert.equal(parsed.searchParams.get('q'),'0001 & next=https://example.test/#?');
  assert.equal(parsed.searchParams.has('next'),false);
});

test('container display converts grams and kilograms exactly without losing partial precision', async () => {
  const { equivalentMass } = await import('../src/inventory/measurements');
  assert.equal(equivalentMass('6', 'kg'), '6000 g');
  assert.equal(equivalentMass('1250', 'g'), '1.25 kg');
  assert.equal(equivalentMass('0.001', 'g'), '0.000001 kg');
  assert.equal(equivalentMass('999999999.999999', 'kg'), '999999999999.999 g');
  assert.equal(equivalentMass('0.000001', 'g'), '0.000000001 kg');
  assert.equal(equivalentMass('6', 'l'), null);
  assert.equal(equivalentMass('NaN', 'kg'), null);
});
test('catalog accepts a bounded alphabetical cursor without treating it as a record ID', async () => {
  const cursor = 'p1.WyJtaWxrIiwiMTExMTExMTEtMTExMS00MTExLTgxMTEtMTExMTExMTExMTExIl0';
  const api = inventoryApi(async <T>() => ({items:[product],nextCursor:cursor}) as T);
  assert.equal((await api.products()).nextCursor,cursor);
  const bad = inventoryApi(async <T>() => ({items:[product],nextCursor:'https://elsewhere.test'}) as T);
  await assert.rejects(bad.products(),ApiError);
});
test('unknown legacy container sizes stay unknown and malformed amounts are rejected', async () => {
  const { containerAmount, ...legacy } = product;
  const api = inventoryApi(async <T>() => legacy as T);
  assert.equal((await api.product(product.id)).containerAmount,null);
  for (const amount of ['-1','NaN',6,'0','1e3','6.1234567']) {
    const invalid = inventoryApi(async <T>() => ({...product,containerAmount:amount}) as T);
    await assert.rejects(invalid.product(product.id),ApiError);
  }
});
