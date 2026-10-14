import React, { useCallback, useState } from 'react';
import { useFocusEffect } from 'expo-router';
import { Body, Button, Card, Field, Heading, Loading, Notice } from '@/src/ui/components';
import { useRememberedState } from '@/src/restoration/WorkspaceProvider';
import { BarcodeCamera } from './BarcodeCamera';
import { ProductForm } from './CatalogProductForm';
import { ProductCard } from './CatalogScreens';
import { type Product } from './api';
import { InventoryPage, InventorySearch, LoadError, Pages, useInventory, useInventoryNavigation, useInventoryResource } from './shared';
import { InventoryItem, InventoryList } from './InventoryItem';

const emptyScan = { code: '', barcodeType: '', lookup: false };

export function CatalogScanScreen() {
  return <CatalogScanner />;
}

function CatalogScanner() {
  const [draft, setDraft] = useRememberedState('inventory.catalog.scan', emptyScan);
  const [cameraOpen, setCameraOpen] = useState(false);
  useFocusEffect(useCallback(() => () => setCameraOpen(false), []));
  const next = (camera: boolean) => { setDraft(emptyScan); setCameraOpen(camera); };
  const scanned = (result: { data: string; type: string }) => {
    setCameraOpen(false);
    setDraft({ code: result.data, barcodeType: result.type, lookup: true });
  };
  if (cameraOpen) return <InventoryPage title="Scan your products." backTo="/catalog" backLabel="Back to scanner" onBack={() => setCameraOpen(false)}><BarcodeCamera onScan={scanned} onClose={() => setCameraOpen(false)} /></InventoryPage>;
  if (draft.lookup) return <ScanLookup key={`${draft.barcodeType}:${draft.code}`} code={draft.code} barcodeType={draft.barcodeType}
    onNext={next} onChange={() => setDraft(value => ({ ...value, lookup: false }))} />;
  return <InventoryPage title="Scan your products." backTo="/catalog"><Card>
    <Heading>Add ingredients, one scan at a time.</Heading>
    <Body muted>Use the product barcode. Delivery stickers may identify a shipment.</Body>
    <Button title="Open camera" icon="camera-outline" onPress={() => setCameraOpen(true)} />
    <Field label="Barcode or SKU" value={draft.code} maxLength={64} autoCapitalize="none" autoCorrect={false}
      returnKeyType="search" hint="Keep any leading zeros."
      onChangeText={code => setDraft({ code, barcodeType: '', lookup: false })}
      onSubmitEditing={() => { if (draft.code.trim()) setDraft(value => ({ ...value, code: value.code.trim(), lookup: true })); }} />
    <Button title="Look up code" variant="secondary" disabled={!draft.code.trim()}
      onPress={() => setDraft(value => ({ ...value, code: value.code.trim(), lookup: true }))} />
    <Body muted>Scanning adds products, not stock quantities.</Body>
  </Card></InventoryPage>;
}

function ScanLookup({ code, barcodeType, onNext, onChange }: {
  code: string; barcodeType: string; onNext: (camera: boolean) => void; onChange: () => void;
}) {
  const { api, canEdit } = useInventory(); const navigation = useInventoryNavigation();
  const [saved, setSaved] = useState<{ product: Product; alreadyExists: boolean } | null>(null);
  const [missingChoice, setMissingChoice] = useRememberedState<'choose' | 'package' | 'product'>(`inventory.catalog.scan.missing.${barcodeType}.${code}`, 'choose');
  const resource = useInventoryResource(useCallback(() => api.lookupProduct(code, barcodeType || undefined), [api, code, barcodeType]));
  const page = (children: React.ReactNode, onBack = onChange, backLabel = 'Back to scanner') => <InventoryPage title="Scan your products." backTo="/catalog" backLabel={backLabel} onBack={onBack}>{children}</InventoryPage>;
  if (resource.loading) return page(<Loading label="Checking the company catalog…" />);
  if (resource.error || !resource.data) return page(<>
    <LoadError {...resource} />
    <Body muted>Scanned code: {code}</Body>
    <Button title="Scan again" icon="camera-outline" onPress={() => onNext(true)} />
    <Button title="Change code" variant="quiet" onPress={onChange} />
  </>);
  const product = saved?.product || resource.data.product;
  const created = saved && !saved.alreadyExists;
  if (product) return page(<>
    <Notice message={created ? `${product.name} was added to the catalog.` : product.active
      ? resource.data.package ? resource.data.package.active ? `${product.name} is already in the catalog as ${resource.data.package.name}.` : `${resource.data.package.name} is linked to ${product.name}, but that package is archived and cannot be counted as stock.` : `${product.name} is already in the catalog.`
      : `${product.name} is already in the catalog, but archived. Open it to review or restore it.`} kind={created ? 'success' : 'info'} />
    <ProductCard item={product} onPress={() => navigation.open({ pathname: '/catalog/[productId]', params: { productId: product.id } })} />
    <Button title="Scan next product" icon="camera-outline" onPress={() => onNext(true)} />
    <Button title="View product" variant="secondary" onPress={() => navigation.open({ pathname: '/catalog/[productId]', params: { productId: product.id } })} />
    <Button title="Enter another code" variant="quiet" onPress={() => onNext(false)} />
  </>);
  if (!canEdit) return page(<Card>
    <Heading>Product not found</Heading>
    <Body>SKU {resource.data.sku}</Body>
    <Notice message="Ask an owner or catalog administrator to add this product." />
    <Button title="Scan next product" icon="camera-outline" onPress={() => onNext(true)} />
    <Button title="Enter another code" variant="quiet" onPress={() => onNext(false)} />
  </Card>);
  if (missingChoice === 'choose') return page(<Card><Heading>Code not found</Heading><Body>New package or new item?</Body><Button title="Add package to existing item" icon="barcode-outline" onPress={() => setMissingChoice('package')} /><Button title="Create new item" variant="secondary" icon="add" onPress={() => setMissingChoice('product')} /><Button title="Enter another code" variant="quiet" onPress={() => onNext(false)} /></Card>);
  if (missingChoice === 'package') return page(<ExistingProductPicker code={code} barcodeType={barcodeType} onCancel={() => setMissingChoice('choose')} />, () => setMissingChoice('choose'), 'Back to code choices');
  return page(<ProductForm scanned={{ sku: resource.data.sku, barcodeType: barcodeType || undefined,
    onSaved: (product, alreadyExists = false) => setSaved({ product, alreadyExists }), onCancel: () => setMissingChoice('choose'), onCheck: () => { void resource.refresh(); } }} />, () => setMissingChoice('choose'), 'Back to code choices');
}

function ExistingProductPicker({ code, barcodeType, onCancel }: { code: string; barcodeType: string; onCancel: () => void }) {
  const { api } = useInventory(); const navigation = useInventoryNavigation();
  const [filters, setFilters] = useRememberedState('inventory.scan.package-product', { query: '', search: '', cursor: '' });
  const resource = useInventoryResource(useCallback(() => api.products(filters.search, 'active', filters.cursor), [api, filters.search, filters.cursor]));
  return <Card><Heading>Add package to an existing item</Heading><Body>Choose the item inside this package.</Body><InventorySearch label="Find the existing item" value={filters.query} onChange={query => setFilters(v => ({ ...v, query }))} submitLabel="Find existing items" onSubmit={() => setFilters(v => ({ ...v, search: v.query.trim(), cursor: '' }))} />{resource.loading ? <Loading label="Finding catalog items…" /> : resource.error || !resource.data ? <LoadError {...resource} /> : <><InventoryList>{resource.data.items.map(item => <InventoryItem key={item.id} title={item.name} subtitle={`SKU ${item.sku}`} label={`Add package to ${item.name}`} icon="add-circle-outline" onPress={() => navigation.open({ pathname: '/catalog/packages/[productId]', params: { productId: item.id, barcode: code, barcodeType } })} />)}</InventoryList><Pages next={resource.data.nextCursor} cursor={filters.cursor} setCursor={cursor => setFilters(v => ({ ...v, cursor }))} /></>}<Button title="Back to choices" variant="quiet" onPress={onCancel} /></Card>;
}
