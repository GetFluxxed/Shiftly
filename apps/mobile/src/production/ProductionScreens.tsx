import React, { useCallback } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import Ionicons from '@expo/vector-icons/Ionicons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Body, Button, Card, EmptyState, Field, Heading, Loading, Notice, Pill, layout } from '@/src/ui/components';
import { Text } from '@/src/ui/Typography';
import { ApiError } from '@/src/api/client';
import { colors, friendlyDate } from '@/src/ui/theme';
import { ActionGrid, ActionTile } from '@/src/ui/ActionGrid';
import { useRememberedState, useWorkspaceCheckpoint } from '@/src/restoration/WorkspaceProvider';
import { InventoryItem, InventoryList } from '@/src/inventory/InventoryItem';
import { LoadError, Pages, useInventoryResource } from '@/src/inventory/shared';
import { newUuid, validProductionId, type ProductionEntry, type ProductionLog, type Recipe } from './api';
import { ProductionPage, useProduction } from './shared';

export type ProductionDraft = { logId: string; requestId: string; businessDate: string; entries: ProductionEntry[]; pending: boolean };
const localDate = () => { const now = new Date(); return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`; };
export const newProductionDraft = (): ProductionDraft => ({ logId: newUuid(), requestId: newUuid(), businessDate: localDate(), entries: [], pending: false });

export function ProductionScreen() {
  const { canSubmit, canManageRecipes } = useProduction(); const router = useRouter();
  return <ProductionPage title="Production"><Card><Heading>Recipes and records</Heading><Body>Choose recipes, record batches, then review stock before confirming.</Body></Card>
    <ActionGrid>{canSubmit ? <ActionTile title="Record today's production" icon="checkmark-done-outline" onPress={() => router.push('/production/run')} /> : null}
      <ActionTile title="Recipe book" icon="restaurant-outline" onPress={() => router.push('/production/recipes')} />
      <ActionTile title="Production history" icon="time-outline" onPress={() => router.push('/production/logs')} />
      {canManageRecipes ? <ActionTile title="New recipe" icon="add-circle-outline" onPress={() => router.push('/production/recipes/new')} /> : null}
    </ActionGrid></ProductionPage>;
}

export function ProductionRunScreen() {
  const { api, canSubmit } = useProduction(); const router = useRouter();
  const [draft, setDraft, reset] = useRememberedState('production.run.draft', newProductionDraft);
  const [cursor, setCursor] = useRememberedState('production.run.recipes.cursor', '');
  const resource = useInventoryResource(useCallback(() => api.recipes('', cursor), [api, cursor]));
  if (!canSubmit) return <ProductionPage title="Today's production"><Card><Body>Your account can view production, but cannot submit what was made.</Body></Card></ProductionPage>;
  if (draft.pending) return <ProductionPage title="Recover production"><Card><Heading>Check the earlier confirmation</Heading><Body>Keep the saved flavors and batches unchanged while Shiftly checks the result.</Body><Button title="Continue" onPress={() => router.replace('/production/review')} /></Card></ProductionPage>;
  const selected = (recipe: Recipe) => draft.entries.find(x => x.recipeId === recipe.id);
  const setBatches = (recipe: Recipe, value: number) => setDraft(v => { const existing = v.entries.some(x => x.recipeId === recipe.id); if (!existing && value >= 1 && v.entries.length >= 100) return v; return { ...v, entries: value < 1 ? v.entries.filter(x => x.recipeId !== recipe.id) : [...v.entries.filter(x => x.recipeId !== recipe.id), { recipeId: recipe.id, revisionId: recipe.revisionId, batches: Math.min(1000, Math.max(1, value)) }] }; });
  return <ProductionPage title="Record production"><Card><Heading>Flavors and batches</Heading><Field label="Business date" value={draft.businessDate} onChangeText={businessDate => setDraft(v => ({ ...v, businessDate }))} maxLength={10} placeholder="YYYY-MM-DD" /><Body muted>Saved on this device. Review stock use before confirming.</Body></Card>
      {resource.loading ? <Loading label="Opening recipes…" /> : resource.error || !resource.data ? <LoadError {...resource} /> : <><InventoryList>{resource.data.items.map(recipe => { const entry = selected(recipe); return <Card key={recipe.id} style={styles.recipeCard}><View style={layout.row}><Pressable accessibilityRole="checkbox" accessibilityLabel={`${entry ? 'Remove' : 'Add'} ${recipe.name}`} accessibilityState={{ checked: !!entry }} onPress={() => setBatches(recipe, entry ? 0 : 1)} style={[styles.checkbox, entry && styles.checked]}><Ionicons name={entry ? 'checkmark' : 'add'} size={20} color={entry ? colors.onPrimary : colors.primary} /></Pressable><View style={layout.flex}><Text style={styles.recipeName}>{recipe.name}</Text><Body muted>Recipe yield: {recipe.yieldAmount} {recipe.yieldUnit}</Body></View></View>
      {entry ? <View style={styles.counter}><Pressable accessibilityRole="button" accessibilityLabel={`Remove one batch of ${recipe.name}`} onPress={() => setBatches(recipe, entry.batches - 1)} style={styles.countButton}><Ionicons name="remove" size={22} color={colors.primary} /></Pressable><View style={styles.countValue}><Text style={styles.countNumber}>{entry.batches}</Text><Text style={styles.countLabel}>batches</Text></View><Pressable accessibilityRole="button" accessibilityLabel={`Add one batch of ${recipe.name}`} accessibilityState={{ disabled: entry.batches >= 1000 }} disabled={entry.batches >= 1000} onPress={() => setBatches(recipe, entry.batches + 1)} style={styles.countButton}><Ionicons name="add" size={22} color={colors.primary} /></Pressable></View> : null}</Card>; })}</InventoryList>
    {!resource.data.items.length ? <Card><EmptyState icon="restaurant-outline" title="No recipes available" description="A manager or owner needs to create a recipe before production can be recorded." /></Card> : null}<Pages next={resource.data.nextCursor} cursor={cursor} setCursor={setCursor} /></>}
    <Card><Heading>Review</Heading><Body>{draft.entries.length ? `${draft.entries.length} flavor${draft.entries.length === 1 ? '' : 's'} selected.` : 'Choose each flavor made.'}</Body><Button title="Review ingredient use" disabled={!draft.entries.length || !/^\d{4}-\d{2}-\d{2}$/.test(draft.businessDate)} onPress={() => router.push('/production/review')} /><Button title="Clear draft" variant="quiet" onPress={reset} /></Card>
  </ProductionPage>;
}

export function ProductionReviewScreen() {
  const { api, actor, canSubmit } = useProduction(); const router = useRouter();
  const [draft, setDraft, reset] = useRememberedState('production.run.draft', newProductionDraft);
  const checkpoint = useWorkspaceCheckpoint();
  const resource = useInventoryResource(useCallback(() => {
    if (!actor || !draft.entries.length) throw new Error('Choose at least one flavor before review.');
    return api.preview(draft.businessDate, draft.entries, actor.storeId);
  }, [api, actor, draft.businessDate, JSON.stringify(draft.entries)]), !draft.pending);
  const [confirming, setConfirming] = React.useState(false); const [error, setError] = React.useState<string | null>(null);
  const checkedPending = React.useRef<string | null>(null);
  const openLog = React.useCallback((id: string) => { reset(); router.replace({ pathname: '/production/logs/[logId]', params: { logId: id } }); }, [reset, router]);
  const checkSaved = React.useCallback(async () => {
    setConfirming(true); setError(null);
    try { openLog((await api.log(draft.logId)).id); }
    catch (failure) { setError(failure instanceof ApiError && failure.status === 404 ? 'No confirmed log yet. Keep this draft and retry it unchanged.' : failure instanceof Error ? failure.message : 'We could not check the earlier production confirmation.'); }
    finally { setConfirming(false); }
  }, [api, draft.logId, openLog]);
  React.useEffect(() => { if (draft.pending && checkedPending.current !== draft.logId) { checkedPending.current = draft.logId; void checkSaved(); } }, [draft.pending, draft.logId, checkSaved]);
  const retrySaved = async () => {
    if (!actor || !draft.pending) return; setConfirming(true); setError(null);
    if (!await checkpoint()) { setError('This production draft is not fully saved on this device. Try again before retrying.'); setConfirming(false); return; }
    try { openLog((await api.confirm(draft.logId, draft.businessDate, draft.entries, draft.requestId, actor.storeId)).id); }
    catch (failure) { if (failure instanceof ApiError && (failure.status === 400 || failure.status === 409)) setDraft(v => ({ ...v, pending: false })); setError(failure instanceof Error ? failure.message : 'We could not recover the saved production.'); }
    finally { setConfirming(false); }
  };
  const confirm = async () => {
    if (!actor || !resource.data?.canConfirm || draft.pending) return; setConfirming(true); setError(null); setDraft(v => ({ ...v, pending: true }));
    if (!await checkpoint()) { setError('Your production draft could not be saved on this device. Try again before confirming.'); setConfirming(false); return; }
    try { const saved = await api.confirm(draft.logId, draft.businessDate, draft.entries, draft.requestId, actor.storeId); reset(); router.replace({ pathname: '/production/logs/[logId]', params: { logId: saved.id } }); }
    catch (e) {
      try { const saved = await api.log(draft.logId); reset(); router.replace({ pathname: '/production/logs/[logId]', params: { logId: saved.id } }); return; }
      catch { if (e instanceof ApiError && (e.status === 400 || e.status === 409)) setDraft(v => ({ ...v, pending: false })); setError(e instanceof Error ? e.message : 'We could not confirm production. Keep this draft and reload before trying again.'); }
    } finally { setConfirming(false); }
  };
  return <ProductionPage title="Review ingredient use"><Notice message={error} kind="error" />{draft.pending ? <Card><Heading>Check the earlier confirmation</Heading><Body>The result is uncertain. Keep this saved production unchanged, then retry or check for its log.</Body><Button title="Retry unchanged production" loading={confirming} onPress={() => { void retrySaved(); }} /><Button title="Check for production log" variant="secondary" disabled={confirming} onPress={() => { void checkSaved(); }} /></Card> : resource.loading ? <Loading label="Adding the 1% consumption allowance…" /> : resource.error || !resource.data ? <LoadError {...resource} /> : <>
    <Card><Heading>Review deductions</Heading><Body>Totals include recipe amounts plus the 1% allowance. Stock changes when you confirm.</Body><Pill label={`${draft.entries.reduce((sum, x) => sum + x.batches, 0)} total batches`} /></Card>
    <Heading>Flavors to confirm</Heading><InventoryList>{resource.data.entries.map((entry, index) => <InventoryItem key={`${entry.recipeId}:${entry.revisionId}:${index}`} title={entry.name} subtitle={`${entry.batches} batch${entry.batches === 1 ? '' : 'es'}`} detail={`Recipe yield: ${entry.yieldAmount} ${entry.yieldUnit}`} />)}</InventoryList>
    {resource.data.issues.map((issue, index) => <Notice key={`${issue.productId}:${issue.code}:${index}`} message={issue.message} kind="error" />)}
    <InventoryList>{resource.data.deductions.map(x => <Card key={x.productId} style={styles.deduction}><Heading>{x.name}</Heading><Body>Recipe amount: {x.recipeAmount} {x.baseUnit}</Body><Body>1% allowance: +{x.allowanceAmount} {x.baseUnit}</Body><View style={layout.divider} /><Body><Text style={styles.strong}>Total deduction: {x.quantity} {x.baseUnit}</Text></Body><Body muted>{x.balance === null ? 'Current stock is unknown.' : `On hand ${x.balance} ${x.baseUnit} · remaining ${x.remaining ?? 'unknown'} ${x.baseUnit}`}</Body></Card>)}</InventoryList>
    {!resource.data.canConfirm ? <Notice message="Production cannot be confirmed yet. Fix unknown or insufficient stock, then refresh this review." kind="error" /> : null}
    <Card><Button title="Confirm production and deduct stock" loading={confirming} disabled={!canSubmit || !resource.data.canConfirm} onPress={() => { void confirm(); }} /><Button title="Back to edit batches" variant="quiet" disabled={confirming} onPress={() => router.replace('/production/run')} /></Card>
  </>}</ProductionPage>;
}

export function ProductionLogsScreen() {
  const { api } = useProduction(); const router = useRouter(); const [cursor, setCursor] = useRememberedState('production.logs.cursor', '');
  const resource = useInventoryResource(useCallback(() => api.logs(cursor), [api, cursor]));
  return <ProductionPage title="Production history">{resource.loading ? <Loading label="Opening production history…" /> : resource.error || !resource.data ? <LoadError {...resource} /> : <>{!resource.data.items.length ? <Card><EmptyState icon="time-outline" title="No production logs yet" description="Confirmed production will appear here." /></Card> : null}<InventoryList>{resource.data.items.map(item => <InventoryItem key={item.id} title={item.businessDate} subtitle={item.state === 'reversed' ? 'Reversed' : 'Confirmed'} detail={`${item.ingredients.length} ingredient deduction${item.ingredients.length === 1 ? '' : 's'}`} onPress={() => router.push({ pathname: '/production/logs/[logId]', params: { logId: item.id } })} />)}</InventoryList><Pages next={resource.data.nextCursor} cursor={cursor} setCursor={setCursor} /></>}</ProductionPage>;
}
export function ProductionLogScreen() { const { logId } = useLocalSearchParams<{ logId: string }>(); return <ProductionPage title="Production log" backTo="/production/logs">{validProductionId(logId) ? <LogDetails id={logId} /> : <Notice message="This production log is unavailable." kind="error" />}</ProductionPage>; }
function LogDetails({ id }: { id: string }) {
  const { api, actor, canManage } = useProduction(); const resource = useInventoryResource(useCallback(() => api.log(id), [api, id])); const [reason, setReason] = React.useState(''); const [busy, setBusy] = React.useState(false); const [error, setError] = React.useState<string | null>(null);
  if (resource.loading) return <Loading label="Opening production log…" />; if (resource.error || !resource.data) return <LoadError {...resource} />; const item: ProductionLog = resource.data;
  const reverse = async () => { if (!actor) return; setBusy(true); setError(null); try { await api.reverse(item.id, reason.trim(), newUuid(), actor.storeId); setReason(''); await resource.refresh(); } catch (e) { setError(e instanceof Error ? e.message : 'This log could not be reversed.'); } finally { setBusy(false); } };
  return <><Card><Heading>{item.businessDate}</Heading><Pill label={item.state} /><Body>Recorded by {item.createdBy} · {friendlyDate(item.createdAt)}</Body>{item.reversalReason ? <Notice message={`Reversal reason: ${item.reversalReason}`} /> : null}</Card><Heading>Flavors made</Heading><InventoryList>{item.entries.map((entry, index) => <InventoryItem key={`${entry.recipeId}:${entry.revisionId}:${index}`} title={entry.name} subtitle={`${entry.batches} batch${entry.batches === 1 ? '' : 'es'}`} detail={`Recipe yield: ${entry.yieldAmount} ${entry.yieldUnit}`} />)}</InventoryList><Heading>Ingredient deductions</Heading><InventoryList>{item.ingredients.map(x => <InventoryItem key={x.productId} title={x.name} subtitle={`Recipe ${x.recipeAmount} + 1% allowance ${x.allowanceAmount} ${x.baseUnit}`} detail={`${x.quantity} ${x.baseUnit} deducted`} />)}</InventoryList>{canManage && item.state === 'confirmed' ? <Card><Heading>Reverse this log</Heading><Notice message={error} kind="error" /><Field label="Reason for reversal" value={reason} onChangeText={setReason} maxLength={500} editable={!busy} /><Button title="Reverse production log" variant="danger" loading={busy} disabled={!reason.trim()} onPress={() => { void reverse(); }} /></Card> : null}</>;
}

const styles = StyleSheet.create({ recipeCard: { padding: 16 }, checkbox: { width: 46, height: 46, borderRadius: 14, borderWidth: 1, borderColor: colors.controlLine, backgroundColor: colors.soft, alignItems: 'center', justifyContent: 'center' }, checked: { backgroundColor: colors.primary, borderColor: colors.primary }, recipeName: { color: colors.ink, fontSize: 17, fontWeight: '700' }, counter: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10 }, countButton: { width: 52, height: 52, borderRadius: 26, backgroundColor: colors.soft, borderWidth: 1, borderColor: colors.controlLine, alignItems: 'center', justifyContent: 'center' }, countValue: { minWidth: 100, alignItems: 'center' }, countNumber: { color: colors.ink, fontSize: 27, fontWeight: '700' }, countLabel: { color: colors.muted, fontSize: 12 }, deduction: { padding: 16 }, strong: { fontWeight: '700', color: colors.ink } });
