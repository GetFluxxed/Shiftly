import React, { useCallback } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import Ionicons from '@expo/vector-icons/Ionicons';
import { useLocalSearchParams } from 'expo-router';
import { Body, Button, Card, EmptyState, Field, Heading, Loading, Notice, Pill, layout } from '@/src/ui/components';
import { Text } from '@/src/ui/Typography';
import { colors } from '@/src/ui/theme';
import { useRememberedState } from '@/src/restoration/WorkspaceProvider';
import { type CombinePreview, type ContainerUnit, type Package, type PackageInput, type PackageKind, validId } from './api';
import { canonicalMassPreview } from './measurements';
import { InventoryItem, InventoryList } from './InventoryItem';
import { InventoryPage, InventorySearch, LoadError, Pages, useInventory, useInventoryNavigation, useInventoryResource } from './shared';

type Draft = { editingId: string; editingVersion: number | null; name: string; kind: PackageKind; amount: string; amountUnit: ContainerUnit; containedPackageId: string; containedCount: string; barcode: string; barcodeType: string };
const empty = (unit: ContainerUnit = 'kg'): Draft => ({ editingId: '', editingVersion: null, name: '', kind: 'container', amount: '', amountUnit: unit, containedPackageId: '', containedCount: '', barcode: '', barcodeType: '' });

export function PackagesScreen() {
  const { productId, barcode = '', barcodeType = '' } = useLocalSearchParams<{ productId: string; barcode?: string; barcodeType?: string }>();
  const navigation = useInventoryNavigation();
  const fallback = validId(productId) ? { pathname: '/catalog/[productId]' as const, params: { productId } } : '/catalog' as const;
  return <InventoryPage title="Packages & barcodes." backTo={fallback} backLabel={navigation.parent(fallback).label}>{validId(productId) ? <PackageManager productId={productId} initialBarcode={barcode} initialBarcodeType={barcodeType} /> : <Notice message="This product is unavailable." kind="error" />}</InventoryPage>;
}

function PackageManager({ productId, initialBarcode, initialBarcodeType }: { productId: string; initialBarcode: string; initialBarcodeType: string }) {
  const { api, identity, canEdit, actor } = useInventory(); const navigation = useInventoryNavigation();
  const productResource = useInventoryResource(useCallback(() => api.product(productId), [api, productId]));
  const resource = useInventoryResource(useCallback(() => api.packages(productId), [api, productId]));
  const draftScope = initialBarcode ? `scan.${initialBarcode}` : 'manual';
  const [draft, setDraft] = useRememberedState(`inventory.product.${productId}.package.v2.${draftScope}`, () => ({ ...empty(), barcode: initialBarcode, barcodeType: initialBarcodeType }));
  const [showForm, setShowForm] = React.useState(Boolean(initialBarcode));
  const [showCombine, setShowCombine] = React.useState(false);
  const [busy, setBusy] = React.useState(false); const [error, setError] = React.useState<string | null>(null);
  React.useEffect(() => { if (draft.editingId || draft.name || draft.barcode) setShowForm(true); }, [draft.editingId, draft.name, draft.barcode]);
  React.useEffect(() => { const base = productResource.data?.baseUnit; if (base && !draft.editingId && !draft.name && !draft.amount && draft.amountUnit === 'kg' && base !== 'kg') setDraft(value => ({ ...value, amountUnit: base as ContainerUnit })); }, [productResource.data?.baseUnit, draft.editingId, draft.name, draft.amount, draft.amountUnit, setDraft]);
  if (productResource.loading || resource.loading) return <Loading label="Opening package options…" />;
  if (productResource.error || !productResource.data) return <LoadError {...productResource} />;
  if (resource.error || !resource.data) return <LoadError {...resource} />;
  const product = productResource.data; const options = resource.data.items;
  const parent = navigation.parent('/catalog').href;
  const parentPath = typeof parent === 'string' ? parent : parent.pathname;
  const dropSourceParent = parentPath === `/catalog/${product.id}`;
  if (product.canonicalProductId) return <Card style={styles.compact}><Heading>{product.name}</Heading><Notice message="This item is linked to its main catalog item. Manage packages and barcodes there." /><Button title="Open the main catalog item" onPress={() => navigation.replace({ pathname: '/catalog/[productId]', params: { productId: product.canonicalProductId! } }, dropSourceParent ? { dropParents: 1 } : undefined)} /></Card>;
  const edit = (item: Package) => { setShowForm(true); setDraft({ editingId: item.id, editingVersion: item.version, name: item.name, kind: item.kind, amount: item.containedPackageId ? '' : item.labelAmount ?? item.amount, amountUnit: item.labelUnit ?? product.baseUnit as ContainerUnit, containedPackageId: item.containedPackageId || '', containedCount: item.containedCount === null ? '' : String(item.containedCount), barcode: item.barcodes[0] || '', barcodeType: '' }); };
  const contained = options.find(item => item.id === draft.containedPackageId);
  const sourcePattern = draft.amountUnit === 'each' ? /^\d{1,9}$/ : draft.amountUnit === 'lb' ? /^\d{1,9}(?:\.\d{1,6})?$/ : /^\d{1,9}(?:\.\d{1,9})?$/;
  const canonical = canonicalMassPreview(draft.amount, draft.amountUnit, product.baseUnit);
  const exactAmount = draft.containedPackageId ? contained && /^\d{1,7}$/.test(draft.containedCount) && Number(draft.containedCount) >= 1 : sourcePattern.test(draft.amount) && Number(draft.amount) > 0 && (draft.amountUnit === 'each' || (canonical !== null && canonical.value !== '0' && /^\d{1,9}(?:\.\d{1,9})?$/.test(canonical.value)));
  const save = async () => {
    setBusy(true); setError(null);
    const fields: PackageInput = { name: draft.name.trim(), kind: draft.kind, ...(draft.containedPackageId ? { containedPackageId: draft.containedPackageId, containedCount: Number(draft.containedCount) } : { amount: draft.amount, amountUnit: draft.amountUnit }), ...(draft.barcode.trim() ? { barcode: draft.barcode.trim(), ...(draft.barcodeType ? { barcodeType: draft.barcodeType } : {}) } : {}) };
    try { if (draft.editingId) { const current = options.find(item => item.id === draft.editingId); if (!current || draft.editingVersion === null) throw new Error('This package changed or is no longer available. Reload it before saving.'); await api.editPackage({ ...current, version: draft.editingVersion }, fields, identity); } else await api.createPackage(product.id, fields, identity); setDraft(empty(product.baseUnit as ContainerUnit)); setShowForm(false); await Promise.all([resource.refresh(), productResource.refresh()]); }
    catch (failure) { setError(failure instanceof Error ? failure.message : 'This package could not be saved.'); } finally { setBusy(false); }
  };
  const changeState = async (item: Package) => { setBusy(true); setError(null); try { await api.packageState(item, !item.active, identity); await Promise.all([resource.refresh(), productResource.refresh()]); } catch (failure) { setError(failure instanceof Error ? failure.message : 'This package could not be updated.'); } finally { setBusy(false); } };
  return <><Card style={styles.compact}><Heading>{product.name}</Heading><Body muted>SKU {product.sku} · Counted in {product.baseUnit}</Body></Card>
    <Notice message={error} kind="error" />
    <Heading>Package options</Heading>{!options.length ? <Card><EmptyState icon="barcode-outline" title="No package options yet" description="Add the containers, boxes, or cases your team receives and counts." /></Card> : null}
    <InventoryList>{options.map(item => <Card key={item.id} style={styles.option}><View style={layout.row}><View style={layout.flex}><Heading>{item.name}</Heading><Body>{item.labelAmount && item.labelUnit ? `${item.labelAmount} ${item.labelUnit === 'lb' ? 'lbs' : item.labelUnit}` : `${item.amount} ${product.baseUnit}`}</Body>{item.labelAmount && item.labelUnit && item.labelUnit !== product.baseUnit ? <Body muted>= {item.amount} {product.baseUnit}</Body> : null}</View><View style={styles.pills}><Pill label={item.active ? item.kind : `Archived ${item.kind}`} />{item.isDefault ? <Pill label="Default" /> : null}</View></View>{item.containedPackageId ? <Body muted>{item.containedCount} × {options.find(candidate => candidate.id === item.containedPackageId)?.name || 'inner package'}</Body> : null}{item.barcodes.length ? <Body muted>{item.barcodes.length} linked barcode{item.barcodes.length === 1 ? '' : 's'}</Body> : null}{canEdit ? <View style={layout.row}><Pressable accessibilityRole="button" accessibilityLabel={`Edit ${item.name}`} disabled={busy} onPress={() => edit(item)} style={styles.icon}><Ionicons name="create-outline" size={22} color={colors.primary} /></Pressable><Button title={item.active ? `Archive ${item.name}` : `Restore ${item.name}`} variant={item.active ? 'quiet' : 'secondary'} disabled={busy} onPress={() => { void changeState(item); }} /></View> : null}</Card>)}</InventoryList>
    {canEdit && !showForm ? <Button title="New package" icon="add" onPress={() => { setDraft(empty(product.baseUnit as ContainerUnit)); setShowForm(true); }} /> : null}
    {canEdit && showForm ? <Card style={styles.compact}><Heading>{draft.editingId ? 'Edit package' : 'Add a package'}</Heading>
      <Field label="Package name" value={draft.name} onChangeText={name => setDraft(v => ({ ...v, name }))} maxLength={120} editable={!busy} placeholder="For example, 1 kg tub" />
      <View style={layout.wrap}>{(['container', 'box', 'case'] as const).map(kind => <Button key={kind} title={`${draft.kind === kind ? '✓ ' : ''}${kind}`} variant="secondary" disabled={busy} onPress={() => setDraft(v => ({ ...v, kind, ...(kind === 'case' ? {} : { containedPackageId: '', containedCount: '' }) }))} />)}</View>
      <Body muted>Net contents. Totals use {product.baseUnit === 'each' ? 'whole items' : product.baseUnit}.</Body>
      {product.baseUnit !== 'each' ? <View style={layout.wrap}>{(['kg', 'g', 'lb'] as const).map(unit => <Button key={unit} title={`${draft.amountUnit === unit ? '✓ ' : ''}${unit === 'lb' ? 'lbs' : unit}`} variant={draft.amountUnit === unit ? 'secondary' : 'quiet'} disabled={busy} onPress={() => setDraft(v => v.amountUnit === unit ? v : ({ ...v, amountUnit: unit, amount: '', containedPackageId: '', containedCount: '' }))} />)}</View> : null}
      <Field label={`Full amount (${draft.amountUnit === 'each' ? 'each' : draft.amountUnit === 'lb' ? 'lbs' : draft.amountUnit})`} value={draft.amount} onChangeText={amount => setDraft(v => ({ ...v, amount, containedPackageId: '', containedCount: '' }))} keyboardType="decimal-pad" maxLength={25} editable={!busy} />
      {draft.amountUnit === 'lb' && canonical ? <Body muted>{draft.amount} lbs = {canonical.rounded ? 'Approx. ' : ''}{canonical.value} {product.baseUnit}</Body> : null}
      {draft.kind === 'case' && options.filter(item => item.active && item.id !== draft.editingId && item.containedPackageId === null).length ? <><Body muted>Or choose an inner package. Count a sealed case only once.</Body><View style={layout.wrap}>{options.filter(item => item.active && item.id !== draft.editingId && item.containedPackageId === null).map(item => <Button key={item.id} title={`${draft.containedPackageId === item.id ? '✓ ' : ''}${item.name}`} variant="quiet" disabled={busy} onPress={() => setDraft(v => ({ ...v, containedPackageId: item.id, amount: '' }))} />)}</View>{draft.containedPackageId ? <Field label={`Number of ${contained?.name || 'inner packages'}`} value={draft.containedCount} onChangeText={containedCount => setDraft(v => ({ ...v, containedCount }))} keyboardType="number-pad" maxLength={7} editable={!busy} /> : null}</> : null}
      <Field label="Barcode (optional)" value={draft.barcode} onChangeText={barcode => setDraft(v => ({ ...v, barcode }))} maxLength={64} editable={!busy} autoCapitalize="none" autoCorrect={false} />
      <Button title={draft.editingId ? 'Save package' : 'Add package'} loading={busy} disabled={!draft.name.trim() || !exactAmount} onPress={() => { void save(); }} />
      <Button title="Cancel package draft" variant="quiet" disabled={busy} onPress={() => { setDraft(empty(product.baseUnit as ContainerUnit)); setShowForm(false); }} />
    </Card> : !canEdit ? <Card><Body>A catalog administrator can manage package options and barcode links.</Body></Card> : null}
    {actor?.role === 'owner' ? showCombine ? <CombineSection sourceId={product.id} onClose={() => setShowCombine(false)} /> : <Button title="Use as a package of another item" variant="quiet" onPress={() => setShowCombine(true)} /> : null}
  </>;
}

function CombineSection({ sourceId, onClose }: { sourceId: string; onClose: () => void }) {
  const { api, identity } = useInventory(); const navigation = useInventoryNavigation();
  const parent = navigation.parent('/catalog').href;
  const parentPath = typeof parent === 'string' ? parent : parent.pathname;
  const dropSourceParent = parentPath === `/catalog/${sourceId}`;
  const [filters, setFilters] = useRememberedState(`inventory.combine.${sourceId}.search`, { query: '', search: '', cursor: '' });
  const [targetId, setTargetId] = React.useState(''); const [preview, setPreview] = React.useState<CombinePreview | null>(null); const [error, setError] = React.useState<string | null>(null); const [busy, setBusy] = React.useState(false);
  const resource = useInventoryResource(useCallback(() => api.products(filters.search, 'active', filters.cursor), [api, filters.search, filters.cursor]));
  const review = async (id: string) => { setTargetId(id); setBusy(true); setError(null); try { setPreview(await api.combinePreview(sourceId, id)); } catch (failure) { setError(failure instanceof Error ? failure.message : 'These items could not be reviewed.'); } finally { setBusy(false); } };
  const combine = async () => { if (!preview) return; setBusy(true); setError(null); try { const target = await api.combine(sourceId, preview, identity); navigation.replace({ pathname: '/catalog/[productId]', params: { productId: target.id } }, dropSourceParent ? { dropParents: 1 } : undefined); } catch (failure) { setError(failure instanceof Error ? failure.message : 'These items could not be combined.'); } finally { setBusy(false); } };
  return <Card style={styles.compact}><Heading>Use as a package of another item</Heading><Body>Combine only identical ingredients sold in different package sizes.</Body><Notice message={error} kind="error" />{preview ? <><Body><Text style={styles.strong}>{preview.source.name}</Text> will become a package of <Text style={styles.strong}>{preview.target.name}</Text>.</Body>{preview.packages.map(item => <Body key={item.id}>{item.name} · {item.amount} {preview.source.baseUnit}</Body>)}<Body muted>{preview.shelves} shelf link{preview.shelves === 1 ? '' : 's'} will move to the main item.</Body>{preview.issues.map(issue => <Notice key={issue} message={issue} kind="error" />)}<Button title="Combine items" variant="danger" loading={busy} disabled={!preview.canCombine} onPress={() => { void combine(); }} /><Button title="Choose a different item" variant="quiet" disabled={busy} onPress={() => { setPreview(null); setTargetId(''); }} /></> : <><InventorySearch label="Find the main catalog item" value={filters.query} onChange={query => setFilters(v => ({ ...v, query }))} submitLabel="Find main item" disabled={busy} onSubmit={() => setFilters(v => ({ ...v, search: v.query.trim(), cursor: '' }))} />{resource.loading ? <Loading label="Finding catalog items…" /> : resource.error || !resource.data ? <LoadError {...resource} /> : <><InventoryList>{resource.data.items.filter(item => item.id !== sourceId).map(item => <InventoryItem key={item.id} title={item.name} subtitle={`SKU ${item.sku}`} label={`Review ${item.name} as the main item`} icon="git-merge-outline" disabled={busy || targetId === item.id} onPress={() => { void review(item.id); }} />)}</InventoryList><Pages next={resource.data.nextCursor} cursor={filters.cursor} setCursor={cursor => setFilters(v => ({ ...v, cursor }))} /></>}</>}<Button title="Close" variant="quiet" disabled={busy} onPress={onClose} /></Card>;
}
const styles = StyleSheet.create({ compact: { padding: 16, gap: 12 }, option: { padding: 16, gap: 10 }, pills: { gap: 6 }, icon: { width: 48, height: 48, borderRadius: 24, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.soft }, strong: { fontWeight: '700', color: colors.ink } });
