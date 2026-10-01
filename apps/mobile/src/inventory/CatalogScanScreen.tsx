import React, { useCallback, useState } from 'react';
import { useFocusEffect, useRouter } from 'expo-router';
import { Body, Button, Card, Field, Heading, Loading, Notice } from '@/src/ui/components';
import { useRememberedState } from '@/src/restoration/WorkspaceProvider';
import { BarcodeCamera } from './BarcodeCamera';
import { ProductForm } from './CatalogProductForm';
import { ProductCard } from './CatalogScreens';
import { type Product } from './api';
import { InventoryPage, LoadError, useInventory, useInventoryResource } from './shared';

const emptyScan = { code: '', barcodeType: '', lookup: false };

export function CatalogScanScreen() {
  return <InventoryPage title="Scan your products." backTo="/catalog"><CatalogScanner /></InventoryPage>;
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
  if (cameraOpen) return <BarcodeCamera onScan={scanned} onClose={() => setCameraOpen(false)} />;
  if (draft.lookup) return <ScanLookup key={`${draft.barcodeType}:${draft.code}`} code={draft.code} barcodeType={draft.barcodeType}
    onNext={next} onChange={() => setDraft(value => ({ ...value, lookup: false }))} />;
  return <Card>
    <Heading>Add ingredients, one scan at a time.</Heading>
    <Body muted>Scan the barcode printed on the product. We’ll find it or help you add it to the company catalog. Delivery stickers may identify a shipment instead of a product.</Body>
    <Button title="Open camera" icon="camera-outline" onPress={() => setCameraOpen(true)} />
    <Field label="Barcode or SKU" value={draft.code} maxLength={64} autoCapitalize="none" autoCorrect={false}
      returnKeyType="search" hint="You can also type the code printed below the barcode. Keep any leading zeros."
      onChangeText={code => setDraft({ code, barcodeType: '', lookup: false })}
      onSubmitEditing={() => { if (draft.code.trim()) setDraft(value => ({ ...value, code: value.code.trim(), lookup: true })); }} />
    <Button title="Look up code" variant="secondary" disabled={!draft.code.trim()}
      onPress={() => setDraft(value => ({ ...value, code: value.code.trim(), lookup: true }))} />
    <Body muted>Adding a product does not change stock. Count inventory when you’re ready to record quantities.</Body>
  </Card>;
}

function ScanLookup({ code, barcodeType, onNext, onChange }: {
  code: string; barcodeType: string; onNext: (camera: boolean) => void; onChange: () => void;
}) {
  const { api, canEdit } = useInventory(); const router = useRouter();
  const [saved, setSaved] = useState<{ product: Product; alreadyExists: boolean } | null>(null);
  const resource = useInventoryResource(useCallback(() => api.lookupProduct(code, barcodeType || undefined), [api, code, barcodeType]));
  if (resource.loading) return <Loading label="Checking the company catalog…" />;
  if (resource.error || !resource.data) return <>
    <LoadError {...resource} />
    <Body muted>Scanned code: {code}</Body>
    <Button title="Scan again" icon="camera-outline" onPress={() => onNext(true)} />
    <Button title="Change code" variant="quiet" onPress={onChange} />
  </>;
  const product = saved?.product || resource.data.product;
  const created = saved && !saved.alreadyExists;
  if (product) return <>
    <Notice message={created ? `${product.name} was added to the catalog.` : product.active
      ? `${product.name} is already in the catalog.`
      : `${product.name} is already in the catalog, but archived. Open it to review or restore it.`} kind={created ? 'success' : 'info'} />
    <ProductCard item={product} onPress={() => router.push({ pathname: '/catalog/[productId]', params: { productId: product.id } })} />
    <Button title="Scan next product" icon="camera-outline" onPress={() => onNext(true)} />
    <Button title="View product" variant="secondary" onPress={() => router.push({ pathname: '/catalog/[productId]', params: { productId: product.id } })} />
    <Button title="Enter another code" variant="quiet" onPress={() => onNext(false)} />
  </>;
  if (!canEdit) return <Card>
    <Heading>Product not found</Heading>
    <Body>SKU {resource.data.sku}</Body>
    <Notice message="Ask an owner or catalog administrator to add this product." />
    <Button title="Scan next product" icon="camera-outline" onPress={() => onNext(true)} />
    <Button title="Enter another code" variant="quiet" onPress={() => onNext(false)} />
  </Card>;
  return <ProductForm scanned={{ sku: resource.data.sku, barcodeType: barcodeType || undefined,
    onSaved: (product, alreadyExists = false) => setSaved({ product, alreadyExists }), onCancel: () => onNext(false), onCheck: () => { void resource.refresh(); } }} />;
}
