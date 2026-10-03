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
  const { equivalentMass, canonicalMassPreview } = await import('../src/inventory/measurements');
  assert.equal(equivalentMass('6', 'kg'), '6000 g');
  assert.equal(equivalentMass('1250', 'g'), '1.25 kg');
  assert.equal(equivalentMass('0.001', 'g'), '0.000001 kg');
  assert.equal(equivalentMass('999999999.999999', 'kg'), '999999999999.999 g');
  assert.equal(equivalentMass('0.000001', 'g'), '0.000000001 kg');
  assert.equal(equivalentMass('6', 'l'), null);
  assert.equal(equivalentMass('NaN', 'kg'), null);
  assert.deepEqual(canonicalMassPreview('50', 'lb', 'kg'), { value: '22.6796185', rounded: false });
  assert.deepEqual(canonicalMassPreview('50', 'lb', 'g'), { value: '22679.6185', rounded: false });
  assert.deepEqual(canonicalMassPreview('0.000001', 'lb', 'kg'), { value: '0.000000454', rounded: true });
  assert.deepEqual(canonicalMassPreview('0.000000001', 'g', 'kg'), { value: '0', rounded: true });
  for (const invalid of ['.5', '-1', '1e2', '0', '1.1234567']) assert.equal(canonicalMassPreview(invalid, 'lb', 'kg'), null);
});

test('product and package responses preserve source labels while accepting legacy replies', async () => {
  const labelled = { ...product, containerAmount:'22.6796185', containerLabelAmount:'50', containerLabelUnit:'lb' };
  const parsed = await inventoryApi(async <T>() => labelled as T).product(product.id);
  assert.equal(parsed.containerLabelAmount, '50'); assert.equal(parsed.containerLabelUnit, 'lb');
  const legacy = await inventoryApi(async <T>() => product as T).product(product.id);
  assert.equal(legacy.containerLabelAmount, null); assert.equal(legacy.containerLabelUnit, null);
  const option = { id:'22222222-2222-4222-8222-222222222222', productId:product.id, name:'50 lb bag', amount:'22.6796185', labelAmount:'50', labelUnit:'lb', kind:'container', active:true, version:1, isDefault:false, containedPackageId:null, containedCount:null, barcodes:[] };
  assert.equal((await inventoryApi(async <T>() => ({items:[option],nextCursor:null}) as T).packages(product.id)).items[0]?.labelUnit, 'lb');
  for (const bad of [{...labelled,containerLabelUnit:null},{...labelled,containerLabelAmount:'1.1234567'},{...labelled,containerLabelAmount:'1.123456789',containerLabelUnit:'g'}]) {
    const api=inventoryApi(async <T>() => bad as T);
    if (bad.containerLabelUnit === 'g') assert.equal((await api.product(product.id)).containerLabelAmount,'1.123456789');
    else await assert.rejects(api.product(product.id),ApiError);
  }
});

test('pounds qualifiers are sent only with known product and package amounts', async () => {
  const calls: {path:string; options?:RequestOptions}[]=[];
  const labelled={...product,containerAmount:'22.6796185',containerLabelAmount:'50',containerLabelUnit:'lb' as const};
  const option={id:'22222222-2222-4222-8222-222222222222',productId:product.id,name:'Bag',amount:'22.6796185',labelAmount:'50',labelUnit:'lb' as const,kind:'container' as const,active:true,version:1,isDefault:false,containedPackageId:null,containedCount:null,barcodes:[]};
  const api=inventoryApi(async <T>(path: string, options?: RequestOptions)=>{calls.push({path,options});return (path.includes('/packages')?option:labelled) as T;});
  await api.createProduct({name:'Milk',sku:'0001',baseUnit:'kg',containerAmount:'50',containerUnit:'lb'},new MutationIdentity());
  assert.equal(calls.at(-1)?.options?.body?.containerUnit,'lb');
  await api.editProduct(labelled,'Milk','0001',new MutationIdentity(),null,'lb');
  assert.equal(calls.at(-1)?.options?.body?.containerUnit,undefined);
  await api.createPackage(product.id,{name:'Bag',kind:'container',amount:'50',amountUnit:'lb'},new MutationIdentity());
  assert.equal(calls.at(-1)?.options?.body?.amountUnit,'lb');
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
  for (const amount of ['-1','NaN',6,'0','1e3','6.1234567891']) {
    const invalid = inventoryApi(async <T>() => ({...product,containerAmount:amount}) as T);
    await assert.rejects(invalid.product(product.id),ApiError);
  }
});

test('barcode lookup preserves text and explicitly distinguishes missing from invalid replies', async () => {
  let sent: RequestOptions | undefined;
  const api = inventoryApi(async <T>(path: string, options?: RequestOptions) => {
    assert.equal(path, '/inventory/products/lookup'); sent = options;
    return { sku: '0036000291452', product: null } as T;
  });
  assert.deepEqual(await api.lookupProduct('036000291452', 'upc_a'), { sku: '0036000291452', product: null, package: null });
  assert.deepEqual(sent?.query, { sku: '036000291452', barcodeType: 'upc_a' });
  for (const reply of [{ sku: '0001' }, { sku: '0001', product: false }, { sku: '../bad?code', product: null }, { sku: '0001', product: { ...product, version: 0 } }]) {
    const invalid = inventoryApi(async <T>() => reply as T);
    await assert.rejects(invalid.lookupProduct('0001'), ApiError);
  }
  const found = inventoryApi(async <T>() => ({ sku: '0001', product: { ...product, active: false } }) as T);
  assert.equal((await found.lookupProduct('0001')).product?.active, false);
});

test('package options preserve exact amounts, contained counts, barcode text, and versioned writes', async () => {
  const option = { id:'22222222-2222-4222-8222-222222222222', productId:product.id, name:'Case of tubs', amount:'10', kind:'case' as const, active:true, version:2, isDefault:false, containedPackageId:'33333333-3333-4333-8333-333333333333', containedCount:10, barcodes:['00001234'] };
  let call: { path:string; options?:RequestOptions } | undefined;
  const api=inventoryApi(async <T>(path:string,options?:RequestOptions)=>{call={path,options};return (path.endsWith('/packages') && options?.method!=='POST' ? {items:[option],nextCursor:null}:option) as T;});
  assert.equal((await api.packages(product.id)).items[0]?.barcodes[0],'00001234');
  const aliases = Array.from({ length: 41 }, (_, index) => `CASE-${index}`);
  const manyAliases = inventoryApi(async <T>() => ({ items: [{ ...option, barcodes: aliases }], nextCursor: null }) as T);
  assert.deepEqual((await manyAliases.packages(product.id)).items[0]?.barcodes, aliases);
  await api.editPackage(option,{name:'Case of tubs',kind:'case',containedPackageId:option.containedPackageId,containedCount:12,barcode:'00001234'},new MutationIdentity());
  assert.equal(call?.options?.body?.version,2); assert.equal(call?.options?.body?.containedCount,12); assert.equal(call?.options?.body?.barcode,'00001234');
});

test('package responses reject inconsistent nesting and non-exact amounts', async () => {
  const base={ id:'22222222-2222-4222-8222-222222222222',productId:product.id,name:'Case',amount:'10',kind:'case',active:true,version:1,isDefault:false,containedPackageId:null,containedCount:null,barcodes:[] };
  for(const option of [{...base,amount:'1e3'},{...base,containedCount:10},{...base,barcodes:[7]}]) {
    const api=inventoryApi(async <T>()=>({items:[option],nextCursor:null}) as T); await assert.rejects(api.packages(product.id),ApiError);
  }
});

test('shelf products require storewide quantities and preserve unknown versus zero', async () => {
  const shelf = { id:'22222222-2222-4222-8222-222222222222', name:'Back shelf', storeId:1, version:1 };
  const api = inventoryApi(async <T>() => ({ ...shelf, products: { items: [{ ...product, storeQuantity:null }, { ...product, id:'33333333-3333-4333-8333-333333333333', storeQuantity:'0' }], nextCursor:null } }) as T);
  const result = await api.shelf(shelf.id);
  assert.equal(result.products.items[0]?.storeQuantity, null);
  assert.equal(result.products.items[1]?.storeQuantity, '0');
  const invalid = inventoryApi(async <T>() => ({ ...shelf, products: { items: [product], nextCursor:null } }) as T);
  await assert.rejects(invalid.shelf(shelf.id), ApiError);
});

test('combine preview is explicit and confirmed combine carries both reviewed versions', async () => {
  const target={...product,id:'44444444-4444-4444-8444-444444444444',name:'Main milk'};
  const preview={source:product,target,sourceVersion:3,targetVersion:5,packages:[],shelves:2,canCombine:true,issues:[]};
  let call: {path:string;options?:RequestOptions}|undefined;
  const api=inventoryApi(async <T>(path:string,options?:RequestOptions)=>{call={path,options};return (path.endsWith('combine-preview')?preview:target) as T;});
  const reviewed=await api.combinePreview(product.id,target.id); assert.equal(reviewed.shelves,2);
  await api.combine(product.id,reviewed,new MutationIdentity());
  assert.equal(call?.options?.body?.targetProductId,target.id); assert.equal(call?.options?.body?.sourceVersion,3); assert.equal(call?.options?.body?.targetVersion,5); assert.equal(call?.options?.body?.confirmed,true);
});

test('barcode creation sends the scanned format and keeps identical retries on one request ID', async () => {
  const calls: RequestOptions[] = [];
  const api = inventoryApi(async <T>(_path: string, options?: RequestOptions) => { calls.push(options!); return product as T; });
  const identity = new MutationIdentity();
  const input = { name: 'Milk', sku: '0036000291452', barcodeType: 'ean13', baseUnit: 'kg' as const, containerAmount: '6' };
  await api.createProduct(input, identity); await api.createProduct(input, identity);
  assert.equal(calls[0]?.body?.barcodeType, 'ean13');
  assert.equal(calls[0]?.body?.sku, '0036000291452');
  assert.equal(calls[0]?.body?.requestId, calls[1]?.body?.requestId);
});


test('measurement context validates scope, blockers and recipe counts', async () => {
  const context = { product, canChangeUnit: true, issues: [], recipeCount: 1 };
  const api = inventoryApi(async <T>() => context as T);
  assert.deepEqual(await api.measurement(product.id), { ...context, product: { ...product, containerLabelAmount: null, containerLabelUnit: null } });
  for (const invalid of [
    { ...context, product: { ...product, id: '44444444-4444-4444-8444-444444444444' } },
    { ...context, recipeCount: -1 }, { ...context, recipeCount: 1.5 },
    { ...context, canChangeUnit: 'yes' }, { ...context, issues: [null] },
  ]) {
    const bad = inventoryApi(async <T>() => invalid as T);
    await assert.rejects(bad.measurement(product.id), ApiError);
  }
});

test('measurement corrections preserve reviewed version, exact values and retry identity', async () => {
  const calls: RequestOptions[] = [];
  const api = inventoryApi(async <T>(path: string, options?: RequestOptions) => {
    assert.equal(path, `/inventory/products/${product.id}/measurement`);
    calls.push(options!); return product as T;
  });
  const identity = new MutationIdentity();
  const fields = { baseUnit: 'kg' as const, containerAmount: '2.5', containerUnit: 'lb' as const, acknowledgeRecipes: true };
  await api.changeMeasurement(product, fields, identity);
  await api.changeMeasurement(product, fields, identity);
  assert.equal(calls[0]?.body?.version, product.version);
  assert.equal(calls[0]?.body?.containerAmount, '2.5');
  assert.equal(calls[0]?.body?.containerUnit, 'lb');
  assert.equal(calls[0]?.body?.acknowledgeRecipes, true);
  assert.equal(calls[0]?.body?.requestId, calls[1]?.body?.requestId);
});
