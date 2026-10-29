import React from 'react';
import {
  AccessibilityInfo, findNodeHandle, KeyboardAvoidingView, Modal, Platform, Pressable,
  ScrollView, StyleSheet, View, useWindowDimensions,
} from 'react-native';
import Ionicons from '@expo/vector-icons/Ionicons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { ApiError } from '@/src/api/client';
import { Text } from '@/src/ui/Typography';
import { Body, Button, Field, Heading, Loading, Notice } from '@/src/ui/components';
import { colors } from '@/src/ui/theme';
import {
  type ContainerUnit, type MeasurementContext, type MeasurementInput, type Product, type StockUnit,
} from './api';
import { useInventory } from './shared';

const countingUnits: { value: StockUnit; label: string }[] = [
  { value: 'each', label: 'Each' },
  { value: 'g', label: 'Grams' },
  { value: 'kg', label: 'Kilograms' },
];
const weightUnits: { value: ContainerUnit; label: string }[] = [
  { value: 'g', label: 'g' },
  { value: 'kg', label: 'kg' },
  { value: 'lb', label: 'lbs' },
];

export function ProductMeasurementModal({ item, onClose, onSaved }: {
  item: Product | null;
  onClose: () => void;
  onSaved: (product: Product) => void | Promise<void>;
}) {
  if (!item) return null;
  return <ProductMeasurementEditor key={`${item.id}:${item.version}`} item={item} onClose={onClose} onSaved={onSaved} />;
}

function ProductMeasurementEditor({ item, onClose, onSaved }: {
  item: Product;
  onClose: () => void;
  onSaved: (product: Product) => void | Promise<void>;
}) {
  const { api, identity, canEdit } = useInventory();
  const { width, height } = useWindowDimensions();
  const insets = useSafeAreaInsets();
  const headingRef = React.useRef<View>(null);
  const mounted = React.useRef(true);
  const [context, setContext] = React.useState<MeasurementContext | null>(null);
  const [targetUnit, setTargetUnit] = React.useState<StockUnit | null>(null);
  const [amount, setAmount] = React.useState('');
  const [amountUnit, setAmountUnit] = React.useState<ContainerUnit>('each');
  const [acknowledgeRecipes, setAcknowledgeRecipes] = React.useState(false);
  const [attemptedBlockedChange, setAttemptedBlockedChange] = React.useState(false);
  const [loading, setLoading] = React.useState(true);
  const [saving, setSaving] = React.useState(false);
  const [stale, setStale] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);

  const applyContext = React.useCallback((next: MeasurementContext) => {
    const product = next.product;
    const supportedUnit = countingUnits.some(option => option.value === product.baseUnit)
      ? product.baseUnit as StockUnit : null;
    setContext(next);
    setTargetUnit(supportedUnit);
    setAmount(supportedUnit ? product.containerLabelAmount ?? product.containerAmount ?? '' : '');
    setAmountUnit(product.containerLabelUnit ?? supportedUnit ?? 'each');
    setAcknowledgeRecipes(false);
    setAttemptedBlockedChange(false);
    setStale(false);
  }, []);

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const latest = await api.measurement(item.id);
      if (mounted.current) applyContext(latest);
    } catch (failure) {
      if (mounted.current) setError(failure instanceof Error ? failure.message : 'This measurement could not be loaded.');
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, [api, applyContext, item.id]);

  React.useEffect(() => { void load(); }, [load]);

  const focusHeading = () => {
    const node = findNodeHandle(headingRef.current);
    if (node) AccessibilityInfo.setAccessibilityFocus(node);
  };
  const locked = saving || loading;
  const close = () => { if (!saving) onClose(); };

  if (!canEdit) return null;
  const phone = width < 700;
  const product = context?.product;
  const baseChanged = Boolean(product && targetUnit && targetUnit !== product.baseUnit);
  const sourceUnits = targetUnit === 'each' ? [{ value: 'each' as const, label: 'each' }] : weightUnits;
  const originalAmount = product?.containerLabelAmount ?? product?.containerAmount ?? '';
  const originalAmountUnit = product?.containerLabelUnit ?? product?.baseUnit;
  const amountChanged = Boolean(product && (amount.trim() !== originalAmount
    || (amount.trim() && amountUnit !== originalAmountUnit)));
  const hasExistingPackage = Boolean(product?.containerAmount);
  const amountRequired = Boolean(product && hasExistingPackage && !amount.trim());
  const validAmount = !amount.trim() || (amountUnit === 'each' ? /^\d{1,9}$/.test(amount.trim())
    : new RegExp(`^\\d{1,9}(?:\\.\\d{1,${amountUnit === 'lb' ? 6 : 9}})?$`).test(amount.trim())) && Number(amount.trim()) > 0;
  const recipesNeedAcknowledgement = Boolean(baseChanged && context && context.recipeCount > 0);
  const changed = baseChanged || amountChanged;
  const dialogName = product?.name ?? item.name;

  const chooseCountingUnit = (value: StockUnit) => {
    if (!context || saving || value === targetUnit) return;
    if (value !== context.product.baseUnit && !context.canChangeUnit) {
      setAttemptedBlockedChange(true);
      return;
    }
    setTargetUnit(value);
    setAmount('');
    setAmountUnit(value);
    setAcknowledgeRecipes(false);
    setAttemptedBlockedChange(false);
    setError(null);
  };
  const chooseAmountUnit = (value: ContainerUnit) => {
    if (saving || value === amountUnit) return;
    setAmountUnit(value);
    setAmount('');
    setError(null);
  };
  const save = async () => {
    if (!context || !product || !targetUnit || !changed || amountRequired || !validAmount
      || (recipesNeedAcknowledgement && !acknowledgeRecipes) || saving || stale) return;
    setSaving(true);
    setError(null);
    try {
      const containerAmount = amount.trim() || null;
      const saved = baseChanged
        ? await api.changeMeasurement(product, {
          baseUnit: targetUnit,
          containerAmount,
          ...(containerAmount ? { containerUnit: amountUnit } : {}),
          acknowledgeRecipes,
        } satisfies MeasurementInput, identity)
        : await api.editProduct(product, product.name, product.sku, identity, containerAmount, amountUnit);
      await onSaved(saved);
      if (mounted.current) onClose();
    } catch (failure) {
      if (!mounted.current) return;
      setError(failure instanceof Error ? failure.message : 'This measurement could not be saved.');
      setStale(failure instanceof ApiError && failure.code === 'stale_record');
    } finally {
      if (mounted.current) setSaving(false);
    }
  };

  return <Modal visible transparent animationType={phone ? 'slide' : 'fade'} statusBarTranslucent
    onShow={focusHeading} onRequestClose={close} accessibilityViewIsModal>
    <View style={[styles.layer, phone ? styles.phoneLayer : styles.wideLayer]}>
      <View style={styles.backdrop} />
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={[styles.dialog, phone
          ? [styles.sheet, { maxHeight: Math.max(0, height - insets.top - 12), paddingBottom: insets.bottom }]
          : [styles.centered, { maxHeight: Math.max(0, height - insets.top - insets.bottom - 48) }]]}>
        <View style={styles.header}>
          <View ref={headingRef} accessible accessibilityRole="header"
            accessibilityLabel={`Change measurement for ${dialogName}`} style={styles.headerTitle}>
            <Heading>Change measurement</Heading>
            <Body muted>{dialogName}</Body>
          </View>
          <Pressable accessibilityRole="button" accessibilityLabel="Close measurement editor"
            accessibilityState={{ disabled: saving }} disabled={saving} onPress={close} style={styles.close}>
            <Ionicons name="close" size={24} color={saving ? colors.muted : colors.primary} accessible={false} />
          </Pressable>
        </View>
        <ScrollView style={styles.scroll} contentContainerStyle={styles.content}
          keyboardShouldPersistTaps="handled" keyboardDismissMode="on-drag">
          {loading ? <Loading label="Loading measurement…" /> : null}
          <Notice message={error} kind="error" />
          {!loading && !context ? <Button title="Retry measurement" variant="secondary" onPress={() => { void load(); }} /> : null}
          {context && product ? <>
            <View style={styles.section} accessibilityRole="radiogroup" accessibilityLabel="Counting unit">
              <Body>Counting unit</Body>
              <View style={styles.options}>{countingUnits.map(option => {
                const selected = targetUnit === option.value;
                return <Pressable key={option.value} accessibilityRole="radio" accessibilityLabel={option.label}
                  accessibilityState={{ checked: selected, disabled: locked }} aria-checked={selected} disabled={locked}
                  onPress={() => chooseCountingUnit(option.value)} style={[styles.option, selected && styles.selectedOption]}>
                  <Ionicons name={selected ? 'checkmark-circle' : 'ellipse-outline'} size={22} color={colors.primary} accessible={false} />
                  <Text style={styles.optionText}>{option.label}</Text>
                </Pressable>;
              })}</View>
            </View>
            {!targetUnit ? <Body muted>Current counting unit: {product.baseUnit === 'l' ? 'Litres (legacy)' : product.baseUnit === 'ml' ? 'Millilitres (legacy)' : product.baseUnit}</Body> : null}
            <Notice message={attemptedBlockedChange
              ? context.issues.join(' ') || 'The counting unit cannot be changed right now.' : null} kind="error" />
            {targetUnit ? <>
            <View style={styles.section} accessibilityRole="radiogroup" accessibilityLabel="Full container unit">
              <Body>Full container unit</Body>
              <View style={styles.options}>{sourceUnits.map(option => {
                const selected = amountUnit === option.value;
                return <Pressable key={option.value} accessibilityRole="radio" accessibilityLabel={option.label}
                  accessibilityState={{ checked: selected, disabled: locked }} aria-checked={selected} disabled={locked}
                  onPress={() => chooseAmountUnit(option.value)} style={[styles.option, selected && styles.selectedOption]}>
                  <Ionicons name={selected ? 'checkmark-circle' : 'ellipse-outline'} size={22} color={colors.primary} accessible={false} />
                  <Text style={styles.optionText}>{option.label}</Text>
                </Pressable>;
              })}</View>
            </View>
            <Field label={`Full container amount (${amountUnit === 'lb' ? 'lbs' : amountUnit === 'each' ? 'items' : amountUnit})`}
              value={amount} onChangeText={setAmount} keyboardType="decimal-pad" maxLength={19} editable={!locked}
              hint={!hasExistingPackage ? 'Leave blank if unknown.' : undefined} />
            {amountRequired ? <Notice message="Enter the full container amount for the existing package." kind="error" /> : null}
            {!validAmount ? <Notice message={amountUnit === 'each'
              ? 'Enter a positive whole number of items.' : 'Enter a positive container amount.'} kind="error" /> : null}
            {targetUnit !== 'each'
              ? <Body muted>For litre-labelled containers, enter the net weight.</Body> : null}
            {recipesNeedAcknowledgement ? <>
              <Notice message={`Update ${context.recipeCount} affected ${context.recipeCount === 1 ? 'recipe' : 'recipes'} before recording production.`} />
              <Pressable accessibilityRole="checkbox" accessibilityLabel="I’ll update the recipes using this item."
                accessibilityState={{ checked: acknowledgeRecipes, disabled: locked }} aria-checked={acknowledgeRecipes} disabled={locked}
                onPress={() => setAcknowledgeRecipes(value => !value)} style={styles.checkbox}>
                <Ionicons name={acknowledgeRecipes ? 'checkbox' : 'square-outline'} size={24} color={colors.primary} accessible={false} />
                <Text style={styles.checkboxText}>I’ll update the recipes using this item.</Text>
              </Pressable>
            </> : null}
            </> : null}
            {stale ? <Button title="Reload measurement" variant="secondary" loading={loading} disabled={saving}
              onPress={() => { void load(); }} /> : null}
          </> : null}
        </ScrollView>
        <View style={styles.footer}>
          <View style={styles.button}><Button title="Cancel" variant="quiet" disabled={saving} onPress={close} /></View>
          <View style={styles.button}><Button title="Save" loading={saving}
            disabled={loading || !context || !targetUnit || !changed || amountRequired || !validAmount
              || (recipesNeedAcknowledgement && !acknowledgeRecipes) || stale}
            onPress={() => { void save(); }} /></View>
        </View>
      </KeyboardAvoidingView>
    </View>
  </Modal>;
}

const styles = StyleSheet.create({
  layer: { flex: 1 },
  phoneLayer: { justifyContent: 'flex-end' },
  wideLayer: { justifyContent: 'center', alignItems: 'center', padding: 28 },
  backdrop: { position: 'absolute', inset: 0, backgroundColor: 'rgba(45,28,18,0.42)' },
  dialog: { width: '100%', backgroundColor: colors.paper, borderWidth: 1, borderColor: colors.line, overflow: 'hidden' },
  sheet: { borderTopLeftRadius: 24, borderTopRightRadius: 24 },
  centered: { maxWidth: 560, borderRadius: 24 },
  header: { minHeight: 68, paddingHorizontal: 18, paddingVertical: 10, backgroundColor: colors.card,
    borderBottomWidth: 1, borderBottomColor: colors.line, flexDirection: 'row', alignItems: 'center',
    justifyContent: 'space-between', gap: 8 },
  headerTitle: { flex: 1, minWidth: 0, gap: 2 },
  close: { width: 48, height: 48, borderRadius: 24, alignItems: 'center', justifyContent: 'center', flexShrink: 0 },
  scroll: { flexShrink: 1 },
  content: { padding: 18, gap: 14 },
  section: { gap: 8 },
  options: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  option: { minHeight: 48, flexGrow: 1, flexBasis: 104, borderWidth: 1, borderColor: colors.controlLine,
    borderRadius: 12, paddingHorizontal: 12, paddingVertical: 10, flexDirection: 'row', gap: 8,
    alignItems: 'center', justifyContent: 'center' },
  selectedOption: { backgroundColor: colors.blush, borderColor: colors.accentStrong },
  optionText: { color: colors.primary, fontSize: 16, fontWeight: '600' },
  checkbox: { minHeight: 48, borderRadius: 12, paddingHorizontal: 12, paddingVertical: 10,
    flexDirection: 'row', gap: 10, alignItems: 'center' },
  checkboxText: { flex: 1, color: colors.ink, fontSize: 15, lineHeight: 22, fontWeight: '600' },
  footer: { flexShrink: 0, padding: 12, paddingHorizontal: 18, backgroundColor: colors.card,
    borderTopWidth: 1, borderTopColor: colors.line, flexDirection: 'row', justifyContent: 'flex-end',
    flexWrap: 'wrap', gap: 8 },
  button: { flexGrow: 1, flexShrink: 1, minWidth: 112, maxWidth: 220 },
});
