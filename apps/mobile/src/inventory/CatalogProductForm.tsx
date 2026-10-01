import React from 'react';
import { Alert, Pressable, StyleSheet, View } from 'react-native';
import { useRouter } from 'expo-router';
import { ApiError } from '@/src/api/client';
import { Text } from '@/src/ui/Typography';
import { colors } from '@/src/ui/theme';
import { Body, Button, Card, Column, Columns, Field, Heading, Notice, Pill, layout } from '@/src/ui/components';
import { useTask } from '@/src/ui/useTask';
import { useRememberedState } from '@/src/restoration/WorkspaceProvider';
import { units, stockUnits, type Product, type StockUnit } from './api';
import { equivalentMass } from './measurements';
import { useInventory } from './shared';

interface ScannedProduct {
  sku: string;
  barcodeType?: string;
  onSaved: (product: Product, alreadyExists?: boolean) => void;
  onCancel: () => void;
  onCheck: () => void;
}
export function ProductForm({ item, refresh, scanned }: { item?: Product; refresh?: () => Promise<void>; scanned?: ScannedProduct }) {
  const { api, identity, canEdit } = useInventory(); const router = useRouter(); const task = useTask();
  const initialDraft = () => ({ name: item?.name || '', sku: item?.sku || scanned?.sku || '', unit: 'each' as StockUnit, amount: item?.containerAmount ?? (item ? '' : '1') });
  const [draft, setDraft, resetDraft] = useRememberedState(scanned ? `inventory.catalog.scanned.${scanned.sku}` : `inventory.catalog.product.${item?.id || 'new'}`, initialDraft, item ? String(item.version) : undefined);
  const { name, sku, unit, amount } = draft;
  const setName = (name: string) => setDraft(value => ({ ...value, name }));
  const setSku = (sku: string) => setDraft(value => ({ ...value, sku }));
  const setAmount = (amount: string) => setDraft(value => ({ ...value, amount }));
  const baseUnit = item?.baseUnit || unit;
  const supported = (stockUnits as readonly string[]).includes(baseUnit);
  const equivalent = equivalentMass(amount.trim(), baseUnit);
  if (!canEdit && !item) return <Notice message="Catalog management permission is required to create products." />;
  const save = () => {
    let alreadyExists = false;
    void task.run(async () => {
    if (item) return api.editProduct(item, name.trim(), sku.trim(), identity, amount.trim() || null);
    try {
      return await api.createProduct({ name: name.trim(), sku: scanned?.sku || sku.trim(), baseUnit: unit,
        containerAmount: amount.trim() || null, ...(scanned?.barcodeType ? { barcodeType: scanned.barcodeType } : {}) }, identity);
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
    else router.replace({ pathname: '/catalog/[productId]', params: { productId: saved.id } });
  }); };
  const changeState = () => {
    if (!item) return;
    Alert.alert(item.active ? 'Archive this company product?' : 'Restore this company product?',
      item.active ? 'This affects every store in your company. Existing shelf references and history remain, but new placements are blocked.' : 'This makes the product available for shelf placement again.',
      [{ text: 'Cancel', style: 'cancel' }, { text: item.active ? 'Archive product' : 'Restore product', style: item.active ? 'destructive' : 'default',
        onPress: () => { void task.run(() => api.productState(item, !item.active, identity), () => { resetDraft(); void refresh?.(); }); } }]);
  };
  return <><Notice message={task.error} kind="error" /><Columns><Column><Card><Heading>{item ? 'Company product' : scanned ? 'New product' : 'Product identity'}</Heading>
    <Body>{scanned ? 'Add this ingredient once for every store.' : 'Names and SKU edits apply to every store using this product. Old SKUs remain reserved for this product.'}</Body>
    {item && !item.active ? <Pill label="Archived" /> : null}
    <Field label="Product name" value={name} onChangeText={setName} maxLength={160} editable={canEdit && !task.pending} />
    <Field label="SKU" value={sku} onChangeText={setSku} maxLength={64} editable={canEdit && !task.pending && !scanned} autoCapitalize="none" autoCorrect={false} hint={scanned ? 'Filled from the barcode. Leading zeros are kept.' : 'Leading zeros are kept. Use letters, numbers, dot, slash, dash or underscore.'} />
  </Card></Column><Column><Card><Heading>Base stock unit</Heading>
    {item ? <><Body>{units[item.baseUnit]}</Body><Body muted>The base unit stays fixed to protect future stock history. Full and partial containers share this SKU. Grams and kilograms can be converted without changing its base unit.</Body></>
      : <View style={scanned ? layout.row : layout.smallGap}>{stockUnits.map(value => {
        const select = () => { if (value !== unit) setDraft(draft => ({ ...draft, unit: value, amount: value === 'each' ? '1' : '' })); };
        return scanned ? <Pressable key={value} accessibilityRole="button" accessibilityLabel={units[value]}
          accessibilityState={{ selected: unit === value, disabled: task.pending }} disabled={task.pending} onPress={select}
          style={[styles.unit, unit === value && styles.selectedUnit]}>
          <Text style={styles.unitText}>{unit === value ? '✓ ' : ''}{value === 'each' ? 'Each' : value}</Text>
        </Pressable> : <Button key={value} title={`${unit === value ? '✓ ' : ''}${units[value]}`} variant={unit === value ? 'secondary' : 'quiet'} disabled={task.pending} onPress={select} />;
      })}</View>}
    {supported ? <><Field label={`Full container amount (${baseUnit === 'each' ? 'items' : baseUnit})`} value={amount} onChangeText={setAmount}
      keyboardType="decimal-pad" maxLength={16} editable={canEdit && !task.pending}
      hint={scanned ? 'Net amount per full container. Leave blank if unknown.' : 'Net contents in one unopened container, excluding packaging. Leave blank if the size is not known yet.'} />
      {equivalent ? <Body muted>One full container = {amount.trim()} {baseUnit} = {equivalent}.</Body> : null}
      <Body muted>{scanned ? 'Stock quantities are recorded separately.' : 'This is the standard container size. Future counts will combine full containers and measured partials under this product.'}</Body></> : null}
    {canEdit ? <>{!scanned ? <Body muted>Draft kept on this device. Save to update the company catalog.</Body> : null}<Button title={item ? 'Save company product' : 'Create product'} loading={task.pending} disabled={!name.trim() || !sku.trim()} onPress={save} /></> : <Body muted>Your account can view this product.</Body>}
    {item && canEdit ? <Button title={item.active ? 'Archive product' : 'Restore product'} variant={item.active ? 'danger' : 'secondary'} disabled={task.pending} onPress={changeState} /> : null}
    {refresh ? <Button title="Discard edits and reload" variant="quiet" disabled={task.pending} onPress={() => { resetDraft(); void refresh(); }} /> : null}
    {scanned && task.error ? <Button title="Check saved product" variant="secondary" disabled={task.pending} onPress={scanned.onCheck} /> : null}
    <Button title={scanned ? 'Cancel' : item ? 'Back to catalog' : 'Cancel and discard draft'} variant="quiet" disabled={task.pending}
      onPress={() => { if (!item) resetDraft(); if (scanned) scanned.onCancel(); else router.replace('/catalog'); }} />
  </Card></Column></Columns></>;
}

const styles = StyleSheet.create({
  unit: { flex: 1, minHeight: 48, borderRadius: 12, borderWidth: 1, borderColor: colors.controlLine,
    alignItems: 'center', justifyContent: 'center', paddingVertical: 10, paddingHorizontal: 8 },
  selectedUnit: { backgroundColor: colors.blush, borderColor: colors.accentStrong },
  unitText: { color: colors.primary, fontSize: 16, fontWeight: '600' },
});
