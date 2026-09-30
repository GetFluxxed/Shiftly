import React, { useCallback, useMemo } from 'react';
import { KeyboardAvoidingView, Modal, Platform, Pressable, ScrollView, StyleSheet, View, useWindowDimensions } from 'react-native';
import Ionicons from '@expo/vector-icons/Ionicons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Body, Button, Card, Column, Columns, Field, Heading, Loading, Notice, Pill, layout } from '@/src/ui/components';
import { Text } from '@/src/ui/Typography';
import { colors, fonts } from '@/src/ui/theme';
import { useRememberedState, useWorkspaceCheckpoint } from '@/src/restoration/WorkspaceProvider';
import { ApiError } from '@/src/api/client';
import { InventorySearch, LoadError, Pages, useInventoryResource } from '@/src/inventory/shared';
import { InventoryItem, InventoryList } from '@/src/inventory/InventoryItem';
import { inventoryApi, units, type Product } from '@/src/inventory/api';
import { newUuid, validAmount, type ProductionUnit, type Recipe, type RecipeInput } from './api';
import { useProduction } from './shared';

type DraftIngredient = RecipeInput['ingredients'][number] & { name: string; sku: string; baseUnit: ProductionUnit };
type RecipeDraft = Omit<RecipeInput, 'ingredients'> & { ingredients: DraftIngredient[]; requestId: string; pending: boolean };
const blank = (): RecipeDraft => ({ name: '', yieldAmount: '4.5', yieldUnit: 'kg', instructions: '', ingredients: [], requestId: newUuid(), pending: false });
const allowedYield = (draft: RecipeDraft) => draft.yieldUnit === 'kg' && (draft.yieldAmount === '4.5' || draft.yieldAmount === '6');

export function RecipeEditorModal({ item, visible, onClose, onSaved }: { item?: Recipe; visible: boolean; onClose: () => void; onSaved: (saved: Recipe) => void }) {
  const { api, actor, request, canManageRecipes } = useProduction();
  const { width, height } = useWindowDimensions();
  const insets = useSafeAreaInsets();
  const initial = () => item ? { name: item.name, yieldAmount: item.yieldAmount, yieldUnit: item.yieldUnit, instructions: item.instructions, ingredients: item.ingredients.map(x => ({ productId: x.productId, name: x.name, sku: x.sku, baseUnit: x.baseUnit, amount: x.amount, unit: x.unit })), requestId: newUuid(), pending: false } : blank();
  const [draft, setDraft, reset] = useRememberedState(`production.recipe.${item?.id || 'new'}`, initial, item ? `${item.version}:${item.revisionId}` : 'new');
  const checkpoint = useWorkspaceCheckpoint();
  const [error, setError] = React.useState<string | null>(null);
  const [saving, setSaving] = React.useState(false);
  const [yieldOpen, setYieldOpen] = React.useState(false);
  const catalog = useMemo(() => inventoryApi(request), [request]);
  const locked = saving || draft.pending;
  const yieldIsAllowed = allowedYield(draft);
  const valid = !!draft.name.trim() && (yieldIsAllowed || draft.pending) && draft.ingredients.length > 0 && draft.ingredients.every(x => validAmount(x.amount, x.unit));
  const close = () => { if (locked) return; setYieldOpen(false); setError(null); reset(); onClose(); };
  const save = async () => {
    if (!actor || !valid) return;
    setSaving(true); setError(null); setDraft(v => ({ ...v, pending: true }));
    try {
      if (!await checkpoint()) throw new ApiError('Your recipe draft could not be saved on this device. Try again before saving.');
      const fields: RecipeInput = { name: draft.name.trim(), yieldAmount: draft.yieldAmount, yieldUnit: draft.yieldUnit.trim(), instructions: draft.instructions.trim(), ingredients: draft.ingredients.map(({ productId, amount, unit }) => ({ productId, amount, unit })) };
      const saved = item ? await api.editRecipe(item, fields, draft.requestId, actor.storeId) : await api.createRecipe(fields, draft.requestId, actor.storeId);
      reset(); onSaved(saved);
    } catch (e) {
      if (e instanceof ApiError && (e.status === 400 || e.status === 409)) setDraft(v => ({ ...v, pending: false }));
      setError(e instanceof Error ? e.message : 'The recipe could not be saved.');
    } finally { setSaving(false); }
  };
  if (!canManageRecipes || !actor) return null;
  const phone = width < 700;
  return <Modal visible={visible || draft.pending} transparent animationType={phone ? 'slide' : 'fade'} statusBarTranslucent onRequestClose={close} accessibilityViewIsModal>
    <View style={[styles.layer, phone ? styles.phoneLayer : styles.wideLayer]} accessibilityLabel={item ? 'Edit Recipe' : 'New Recipe'}>
      <View style={styles.backdrop} />
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={[styles.dialog, phone ? [styles.sheet, { height: Math.min(height * 0.94, Math.max(0, height - insets.top - 12)), paddingBottom: insets.bottom }] : [styles.centered, { height: Math.max(0, Math.min(height - 64 - insets.top - insets.bottom, 860)) }]]}>
        <View style={styles.header}><View style={layout.flex}><Text style={styles.eyebrow}>Recipe</Text><Text accessibilityRole="header" style={styles.title}>{item ? 'Edit Recipe' : 'New Recipe'}</Text></View>
          <Pressable accessibilityRole="button" accessibilityLabel="Close recipe editor" accessibilityState={{ disabled: locked }} disabled={locked} onPress={close} style={styles.close}><Ionicons name="close" size={25} color={locked ? colors.muted : colors.primary} /></Pressable></View>
        <ScrollView style={styles.scroll} contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled" keyboardDismissMode="on-drag">
          <Notice message={error} kind="error" />
          <Columns><Column><Card><Heading>Recipe</Heading>
            <Field label="Recipe name" value={draft.name} onChangeText={name => setDraft(v => ({ ...v, name }))} maxLength={120} editable={!locked} placeholder="For example, Vanilla bean" />
            <YieldSelector draft={draft} open={yieldOpen} disabled={locked} onToggle={() => setYieldOpen(v => !v)} onSelect={yieldAmount => { setDraft(v => ({ ...v, yieldAmount, yieldUnit: 'kg' })); setYieldOpen(false); }} />
            {!yieldIsAllowed && !draft.pending ? <Notice message={`This recipe currently makes ${draft.yieldAmount} ${draft.yieldUnit}. Choose 4.5 kg or 6 kg before saving changes.`} /> : null}
            <Field label="Instructions (optional)" value={draft.instructions} onChangeText={instructions => setDraft(v => ({ ...v, instructions }))} multiline style={{ minHeight: 110 }} maxLength={4000} editable={!locked} placeholder="Add the steps your crew needs to make this flavor." />
            {draft.pending && !saving ? <Notice message="We could not verify the last save. Retry this unchanged recipe to recover its result. Editing and Cancel stay locked until it is resolved." /> : null}
            <Body muted>Draft kept on this device until you save or cancel.</Body>
          </Card><SelectedIngredients draft={draft} disabled={locked} setDraft={setDraft} /></Column>
          <Column><ProductPicker catalog={catalog} selected={draft.ingredients.map(x => x.productId)} disabled={locked || draft.ingredients.length >= 50} onAdd={product => setDraft(v => v.ingredients.length >= 50 ? v : ({ ...v, ingredients: [...v.ingredients, { productId: product.id, name: product.name, sku: product.sku, baseUnit: product.baseUnit as ProductionUnit, amount: '1', unit: product.baseUnit === 'each' ? 'each' : product.baseUnit === 'kg' ? 'kg' : 'g' }] }))} /></Column></Columns>
        </ScrollView>
        <View style={styles.footer}><View style={styles.footerButton}><Button title="Cancel" variant="quiet" disabled={locked} onPress={close} /></View><View style={styles.footerButton}><Button title={draft.pending && !saving ? 'Retry unchanged recipe save' : 'Save Recipe'} loading={saving} disabled={!valid} onPress={() => { void save(); }} /></View></View>
      </KeyboardAvoidingView>
    </View>
  </Modal>;
}

function YieldSelector({ draft, open, disabled, onToggle, onSelect }: { draft: RecipeDraft; open: boolean; disabled: boolean; onToggle: () => void; onSelect: (amount: '4.5' | '6') => void }) {
  return <View style={styles.yieldField}><Text style={styles.label}>Recipe yield</Text>
    <Pressable accessibilityRole="button" accessibilityLabel="Recipe yield" accessibilityState={{ expanded: open, disabled }} disabled={disabled} onPress={onToggle} style={[styles.trigger, disabled && styles.disabled]}><Text style={styles.value}>{draft.yieldAmount} {draft.yieldUnit}</Text><Ionicons name={open ? 'chevron-up' : 'chevron-down'} size={20} color={colors.primary} /></Pressable>
    {open ? <View style={styles.options}>{(['4.5', '6'] as const).map(amount => { const label = `${amount} kg`; const selected = draft.yieldUnit === 'kg' && draft.yieldAmount === amount; return <Pressable key={amount} accessibilityRole="radio" accessibilityLabel={label} accessibilityState={{ checked: selected, disabled }} disabled={disabled} onPress={() => onSelect(amount)} style={[styles.option, selected && styles.optionSelected]}><Ionicons name={selected ? 'checkmark-circle' : 'ellipse-outline'} size={22} color={colors.primary} /><Text style={styles.value}>{label}</Text></Pressable>; })}</View> : null}
  </View>;
}

function SelectedIngredients({ draft, disabled, setDraft }: { draft: RecipeDraft; disabled: boolean; setDraft: React.Dispatch<React.SetStateAction<RecipeDraft>> }) {
  const setIngredient = (index: number, change: Partial<DraftIngredient>) => setDraft(v => ({ ...v, ingredients: v.ingredients.map((x, i) => i === index ? { ...x, ...change } : x) }));
  return <><Heading>Recipe ingredients</Heading>{!draft.ingredients.length ? <Card><Body>Choose ingredients from the catalog. Nothing is added until you pick it.</Body></Card> : null}<InventoryList>{draft.ingredients.map((x, index) => <Card key={x.productId} style={styles.ingredient}><View style={layout.row}><View style={layout.flex}><Text style={styles.ingredientName}>{x.name}</Text><Body muted>SKU {x.sku}</Body></View><Pressable accessibilityRole="button" accessibilityLabel={`Remove ${x.name}`} disabled={disabled} onPress={() => setDraft(v => ({ ...v, ingredients: v.ingredients.filter(y => y.productId !== x.productId) }))} style={styles.iconButton}><Ionicons name="remove-circle-outline" size={25} color={colors.danger} /></Pressable></View><View style={layout.row}><View style={layout.flex}><Field label="Amount" value={x.amount} onChangeText={amount => setIngredient(index, { amount })} keyboardType="decimal-pad" editable={!disabled} hint={!validAmount(x.amount, x.unit) ? (x.unit === 'each' ? 'Enter a whole item count.' : 'Enter an amount greater than zero.') : undefined} /></View><View style={layout.flex}><Text style={styles.label}>Unit</Text>{x.baseUnit === 'each' ? <Pill label="each" /> : <View style={styles.units}>{(['g', 'kg'] as const).map(unit => <Pressable key={unit} accessibilityRole="button" accessibilityLabel={`Use ${unit} for ${x.name}`} accessibilityState={{ selected: x.unit === unit, disabled }} disabled={disabled} onPress={() => setIngredient(index, { unit })} style={[styles.unitButton, x.unit === unit && styles.unitSelected]}><Text style={[styles.unitText, x.unit === unit && styles.unitTextSelected]}>{unit}</Text></Pressable>)}</View>}<Text style={styles.hint}>SKU base: {x.baseUnit}</Text></View></View></Card>)}</InventoryList></>;
}

function ProductPicker({ catalog, selected, disabled, onAdd }: { catalog: ReturnType<typeof inventoryApi>; selected: string[]; disabled: boolean; onAdd: (product: Product) => void }) {
  const [filters, setFilters] = useRememberedState('production.recipe.catalog', { query: '', search: '', cursor: '' });
  const resource = useInventoryResource(useCallback(() => catalog.products(filters.search, 'active', filters.cursor), [catalog, filters.search, filters.cursor]));
  return <Card><Heading>Add an ingredient</Heading><Body>Pick from the company catalog. Products stay A–Z across pages.</Body><InventorySearch label="Find a catalog product" value={filters.query} onChange={query => setFilters(v => ({ ...v, query }))} submitLabel="Find products" disabled={disabled} onSubmit={() => setFilters(v => ({ ...v, search: v.query.trim(), cursor: '' }))} />{resource.loading ? <Loading label="Finding ingredients…" /> : resource.error || !resource.data ? <LoadError {...resource} /> : <><InventoryList>{resource.data.items.map(p => <InventoryItem key={p.id} title={p.name} subtitle={`SKU ${p.sku} · ${units[p.baseUnit]}`} label={selected.includes(p.id) ? `${p.name} is already in the recipe` : `Add ${p.name}`} icon={selected.includes(p.id) ? 'checkmark-circle-outline' : 'add-circle-outline'} disabled={disabled || selected.includes(p.id)} onPress={() => onAdd(p)} />)}</InventoryList><Pages next={resource.data.nextCursor} cursor={filters.cursor} setCursor={cursor => setFilters(v => ({ ...v, cursor }))} /></>}</Card>;
}

const styles = StyleSheet.create({
  layer: { flex: 1 }, phoneLayer: { justifyContent: 'flex-end' }, wideLayer: { justifyContent: 'center', alignItems: 'center', padding: 32 }, backdrop: { position: 'absolute', inset: 0, backgroundColor: 'rgba(45,28,18,0.42)' },
  dialog: { backgroundColor: colors.paper, overflow: 'hidden', borderColor: colors.line }, sheet: { width: '100%', height: '94%', borderTopLeftRadius: 24, borderTopRightRadius: 24, borderWidth: 1 }, centered: { width: '100%', maxWidth: 980, borderRadius: 24, borderWidth: 1 },
  header: { minHeight: 76, paddingHorizontal: 22, paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: colors.line, backgroundColor: colors.card, flexDirection: 'row', alignItems: 'center', gap: 12 }, eyebrow: { color: colors.accentStrong, fontSize: 12, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 1.2 }, title: { color: colors.ink, fontFamily: fonts.display, fontSize: 28, lineHeight: 33 }, close: { width: 48, height: 48, alignItems: 'center', justifyContent: 'center', borderRadius: 24 },
  scroll: { flex: 1 }, content: { padding: 18, paddingBottom: 28, gap: 18 }, footer: { padding: 12, paddingHorizontal: 18, borderTopWidth: 1, borderTopColor: colors.line, backgroundColor: colors.card, flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'flex-end', gap: 8 }, footerButton: { flexGrow: 1, flexShrink: 1, minWidth: 124, maxWidth: 240 },
  yieldField: { gap: 8 }, label: { color: colors.ink, fontSize: 14, fontWeight: '600', marginBottom: 8 }, trigger: { minHeight: 54, paddingHorizontal: 16, borderWidth: 1, borderColor: colors.controlLine, backgroundColor: colors.white, borderRadius: 12, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 }, value: { color: colors.ink, fontSize: 16, fontWeight: '600' }, options: { borderWidth: 1, borderColor: colors.line, borderRadius: 12, overflow: 'hidden', backgroundColor: colors.white }, option: { minHeight: 50, paddingHorizontal: 16, flexDirection: 'row', alignItems: 'center', gap: 10, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.line }, optionSelected: { backgroundColor: colors.blush }, disabled: { opacity: 0.55 },
  ingredient: { padding: 16, gap: 12 }, ingredientName: { color: colors.ink, fontSize: 16, fontWeight: '700' }, iconButton: { width: 46, height: 46, alignItems: 'center', justifyContent: 'center', borderRadius: 23 }, units: { flexDirection: 'row', gap: 6 }, unitButton: { flex: 1, minHeight: 44, borderRadius: 12, borderWidth: 1, borderColor: colors.controlLine, backgroundColor: colors.soft, alignItems: 'center', justifyContent: 'center' }, unitSelected: { backgroundColor: colors.primary, borderColor: colors.primary }, unitText: { color: colors.primary, fontWeight: '700' }, unitTextSelected: { color: colors.onPrimary }, hint: { color: colors.muted, fontSize: 12, marginTop: 7 },
});
