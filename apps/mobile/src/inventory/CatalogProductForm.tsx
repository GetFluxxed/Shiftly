import React from 'react';
import { Alert, Pressable, StyleSheet, View } from 'react-native';
import Ionicons from '@expo/vector-icons/Ionicons';
import { ApiError } from '@/src/api/client';
import { Text } from '@/src/ui/Typography';
import { colors } from '@/src/ui/theme';
import { Body, Button, Card, Column, Columns, Field, Heading, Notice, Pill, layout } from '@/src/ui/components';
import { useTask } from '@/src/ui/useTask';
import { useRememberedState } from '@/src/restoration/WorkspaceProvider';
import { containerLabel, units, type ContainerUnit, type Product, type StockUnit } from './api';
import { canonicalMassPreview, equivalentMass } from './measurements';
import { useInventory, useInventoryNavigation } from './shared';
import { ProductMeasurementModal } from './ProductMeasurementModal';

interface ScannedProduct {
  sku: string;
  barcodeType?: string;
  onSaved: (product: Product, alreadyExists?: boolean) => void;
  onCancel: () => void;
  onCheck: () => void;
}
export function ProductForm({ item, refresh, refreshing = false, scanned }: {
  item?: Product;
  refresh?: (options?: { preserveData?: boolean }) => Promise<void>;
  refreshing?: boolean;
  scanned?: ScannedProduct;
}) {
  const { api, identity, canEdit } = useInventory(); const navigation = useInventoryNavigation(); const task = useTask();
  const [measurementOpen, setMeasurementOpen] = React.useState(false);
  const parent = navigation.parent('/catalog');
  const initialDraft = () => ({ name: item?.name || '', sku: item?.sku || scanned?.sku || '', unit: 'each' as StockUnit, amount: item?.containerLabelAmount ?? item?.containerAmount ?? (item ? '' : '1'), amountUnit: (item?.containerLabelUnit ?? item?.baseUnit ?? 'each') as ContainerUnit });
  const [draft, setDraft, resetDraft] = useRememberedState(scanned ? `inventory.catalog.scanned.v2.${scanned.sku}` : `inventory.catalog.product.v2.${item?.id || 'new'}`, initialDraft, item ? String(item.version) : undefined);
  const { name, sku, unit, amount, amountUnit } = draft;
  const setName = (name: string) => setDraft(value => ({ ...value, name }));
  const setSku = (sku: string) => setDraft(value => ({ ...value, sku }));
  const setAmount = (amount: string) => setDraft(value => ({ ...value, amount }));
  const baseUnit = item?.baseUnit || unit;
  const supported = ['each', 'g', 'kg'].includes(baseUnit);
  const equivalent = equivalentMass(amount.trim(), amountUnit);
  const canonical = canonicalMassPreview(amount.trim(), amountUnit, baseUnit);
  const identityDirty = Boolean(item && (name !== item.name || sku !== item.sku));
  if (!canEdit && !item) return <Notice message="Catalog management permission is required to create products." />;
  const save = () => {
    let alreadyExists = false;
    void task.run(async () => {
    if (item) return api.editProduct(item, name.trim(), sku.trim(), identity);
    try {
      return await api.createProduct({ name: name.trim(), sku: scanned?.sku || sku.trim(), baseUnit: unit,
        containerAmount: amount.trim() || null, ...(amount.trim() ? { containerUnit: amountUnit } : {}), ...(scanned?.barcodeType ? { barcodeType: scanned.barcodeType } : {}) }, identity);
    } catch (error) {
      // Another person may have added this code after our lookup. Open that product.
      if (scanned && error instanceof ApiError && error.code === 'duplicate_identifier') {
        const found = await api.lookupProduct(scanned.sku, scanned.barcodeType);
        if (found.product) { alreadyExists = true; return found.product; }
      }
      throw error;
    }
  }, saved => {
    resetDraft();
    if (scanned) scanned.onSaved(saved, alreadyExists);
    else if (refresh) void refresh();
    else navigation.replace({ pathname: '/catalog/[productId]', params: { productId: saved.id } });
  }); };
  const changeState = () => {
    if (!item) return;
    Alert.alert(item.active ? 'Archive this company product?' : 'Restore this company product?',
      item.active ? 'This affects every store in your company. Existing shelf references and history remain, but new placements are blocked.' : 'This makes the product available for shelf placement again.',
      [{ text: 'Cancel', style: 'cancel' }, { text: item.active ? 'Archive product' : 'Restore product', style: item.active ? 'destructive' : 'default',
        onPress: () => { void task.run(() => api.productState(item, !item.active, identity), () => { resetDraft(); void refresh?.(); }); } }]);
  };
  return <><Notice message={task.error} kind="error" /><Columns><Column><Card><Heading>{item ? 'Company product' : scanned ? 'New product' : 'Product identity'}</Heading>
    {scanned ? <Body>Add this ingredient to the company catalog.</Body> : null}
    {item && !item.active ? <Pill label="Archived" /> : null}
    <Field label="Product name" value={name} onChangeText={setName} maxLength={160} editable={canEdit && !task.pending} />
    <Field label="SKU" value={sku} onChangeText={setSku} maxLength={64} editable={canEdit && !task.pending && !scanned} autoCapitalize="none" autoCorrect={false}
      hint={scanned ? 'Filled from the barcode. Leading zeros are kept.' : item ? 'Previous codes still find this item.' : 'Leading zeros are kept. Use letters, numbers, dot, slash, dash or underscore.'} />
    {item ? <>
      {canEdit ? <Button title="Save company product" loading={task.pending} disabled={!name.trim() || !sku.trim()} onPress={save} /> : <Body muted>Your account can view this product.</Body>}
      {canEdit ? <Button title={item.active ? 'Archive product' : 'Restore product'} variant={item.active ? 'danger' : 'secondary'} disabled={task.pending} onPress={changeState} /> : null}
      {refresh ? <Button title="Discard edits and reload" variant="quiet" disabled={task.pending} onPress={() => { resetDraft(); void refresh(); }} /> : null}
      <Button title={parent.label} variant="quiet" disabled={task.pending} onPress={() => navigation.back('/catalog')} />
    </> : null}
  </Card></Column><Column><Card><Heading>Measurement</Heading>
    {item ? <>
      <View style={styles.measurementRow}><Body muted>Counting unit</Body><Body>{units[item.baseUnit]}</Body></View>
      <View style={styles.measurementRow}><Body muted>Full container</Body><Body>{item.containerAmount === null ? 'Not set' : containerLabel(item).replace(/^Full container:\s*/, '')}</Body></View>
      {canEdit ? <Pressable accessibilityRole="button" accessibilityLabel={`Change measurement: ${item.name}`}
        accessibilityState={{ disabled: task.pending || refreshing || identityDirty }} disabled={task.pending || refreshing || identityDirty}
        onPress={() => setMeasurementOpen(true)} style={({ pressed }) => [styles.change, (task.pending || refreshing || identityDirty) && styles.disabled, pressed && styles.pressed]}>
        <Ionicons name="resize-outline" size={20} color={colors.primary} accessible={false} />
        <Text style={styles.changeText}>Change</Text>
      </Pressable> : null}
      {identityDirty ? <Body muted>Save or discard the product name and SKU changes before changing measurement.</Body> : null}
    </> : <View style={scanned ? layout.row : layout.smallGap}>{([{ base: 'each', source: 'each', label: 'Each' }, { base: 'g', source: 'g', label: 'Grams' }, { base: 'kg', source: 'kg', label: 'Kilograms' }, { base: 'kg', source: 'lb', label: 'Pounds (lbs)' }] as const).map(value => {
        const selected = unit === value.base && amountUnit === value.source;
        const select = () => { if (!selected) setDraft(draft => ({ ...draft, unit: value.base, amountUnit: value.source, amount: value.base === 'each' ? '1' : '' })); };
        return scanned ? <Pressable key={value.source} accessibilityRole="button" accessibilityLabel={value.label}
          accessibilityState={{ selected, disabled: task.pending }} disabled={task.pending} onPress={select}
          style={[styles.unit, selected && styles.selectedUnit]}>
          <Text style={styles.unitText}>{selected ? '✓ ' : ''}{value.label}</Text>
        </Pressable> : <Button key={value.source} title={`${selected ? '✓ ' : ''}${value.label}`} variant={selected ? 'secondary' : 'quiet'} disabled={task.pending} onPress={select} />;
      })}</View>}
    {!item && supported ? <><Field label={`Full container amount (${amountUnit === 'each' ? 'items' : amountUnit === 'lb' ? 'lbs' : amountUnit})`} value={amount} onChangeText={setAmount}
      keyboardType="decimal-pad" maxLength={19} editable={canEdit && !task.pending}
      hint="Net amount in one unopened container. Leave blank if unknown." />
      {amountUnit === 'lb' ? <Body muted>{canonical ? <>One full container = {amount.trim()} lbs = {canonical.rounded ? 'Approx. ' : ''}{canonical.value} {baseUnit}. </> : null}Inventory totals use {baseUnit}.</Body> : equivalent ? <Body muted>One full container = {amount.trim()} {amountUnit} = {equivalent}.</Body> : canonical && canonical.rounded ? <Body muted>One full container = {amount.trim()} {amountUnit} = Approx. {canonical.value} {baseUnit}.</Body> : null}
    </> : null}
    {!item && canEdit ? <><Button title="Create product" loading={task.pending} disabled={!name.trim() || !sku.trim()} onPress={save} /></> : !item ? <Body muted>Your account can view this product.</Body> : null}
    {scanned && task.error ? <Button title="Check saved product" variant="secondary" disabled={task.pending} onPress={scanned.onCheck} /> : null}
    {!item ? <Button title={scanned ? 'Back to choices' : 'Cancel and discard draft'} variant="quiet" disabled={task.pending}
      onPress={() => { if (!scanned) resetDraft(); if (scanned) scanned.onCancel(); else navigation.back('/catalog'); }} /> : null}
  </Card></Column></Columns>
  <ProductMeasurementModal item={measurementOpen ? item || null : null} onClose={() => setMeasurementOpen(false)}
    onSaved={async () => { await refresh?.({ preserveData: true }); }} />
  </>;
}

const styles = StyleSheet.create({
  unit: { flexGrow: 1, flexBasis: 104, minHeight: 48, borderRadius: 12, borderWidth: 1, borderColor: colors.controlLine,
    alignItems: 'center', justifyContent: 'center', paddingVertical: 10, paddingHorizontal: 8 },
  selectedUnit: { backgroundColor: colors.blush, borderColor: colors.accentStrong },
  unitText: { color: colors.primary, fontSize: 16, fontWeight: '600' },
  measurementRow: { gap: 2 },
  change: { minHeight: 48, alignSelf: 'flex-start', borderRadius: 24, paddingHorizontal: 16, paddingVertical: 12,
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8 },
  changeText: { color: colors.primary, fontSize: 16, fontWeight: '700' },
  disabled: { opacity: 0.55 },
  pressed: { backgroundColor: colors.blush },
});
