import React, { useEffect, useState } from 'react';
import { Pressable, StyleSheet, TextInput, View, useWindowDimensions } from 'react-native';
import Ionicons from '@expo/vector-icons/Ionicons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Body, Button, Loading, Notice, Screen } from '@/src/ui/components';
import { Text, useFontsReady } from '@/src/ui/Typography';
import { colors, fonts } from '@/src/ui/theme';
import { useRememberedState } from '@/src/restoration/WorkspaceProvider';
import { validId } from '../api';
import { LoadError, Pages, useInventoryNavigation } from '../shared';
import { countRouteParams, useCounts } from './shared';
import { quantityLabel } from './measurements';
import type { Count, CountLine } from './api';
import { useOfflineCount } from './OfflineCountsProvider';
import { CountSyncControl } from './CountSyncControl';
import { CountEntrySheet } from './CountEntrySheet';
import { CountShelfPicker, type CountShelfChoice } from './CountShelfPicker';
import { usePageBack } from '@/src/navigation/usePageBack';

const countStates = { draft: 'Draft', review: 'Awaiting approval', posted: 'Finalized', cancelled: 'Cancelled' } as const;

export function CountWorkspaceScreen({ id, returnTo, offlineMode = false, onOfflineScans }: { id: string; returnTo?: string; offlineMode?: boolean; onOfflineScans?: () => void }) {
  const { actor, stores, status, retry } = useCounts();
  const nav = useInventoryNavigation();
  const offline = useOfflineCount();
  const { controller } = offline;
  const { width, fontScale } = useWindowDimensions();
  const insets = useSafeAreaInsets();
  const footerInset = offlineMode || width >= 1000 && fontScale < 1.5 ? insets.bottom : 0;
  const allowed = !!actor?.capabilities.includes('inventory.view') && validId(id);
  useEffect(() => { if (allowed) void controller.open(id).catch(() => undefined); }, [controller, id, allowed]);
  const count = offline.count?.id === id && offline.count.storeId === actor?.storeId ? offline.count : null;
  const storeName = stores.find(store => store.storeId === actor?.storeId)?.storeName || 'Current store';
  const backTo = { pathname: '/counts', params: countRouteParams(returnTo) } as const;
  const back = () => {
    if (offlineMode) void retry();
    else nav.back(backTo);
  };
  usePageBack(back);
  const pending = offline.pendingLineIds.length > 0;
  const reviewDisabled = status !== 'ready' || pending || offline.syncing || offline.status !== 'ready'
    || !!offline.error || !!count?.catalogProductsAvailable || !!(count && count.totalLines > offline.lines.length);
  const review = () => {
    if (reviewDisabled) return;
    nav.open({ pathname: '/counts/[countId]/review', params: { countId: id, ...countRouteParams(returnTo) } });
  };
  const remaining = count ? count.totalProducts - count.countedProducts : 0;
  return <Screen title="Count" compact header={<View style={styles.header}>
    <View style={styles.headerTop}>
      <Pressable accessibilityRole="button" accessibilityLabel={offlineMode ? 'Reconnect to Shiftly' : nav.parent(backTo).label}
        onPress={back} style={styles.back}>
        <Ionicons name={offlineMode ? 'refresh-outline' : 'arrow-back'} size={20} color={colors.primary} />
        <Text style={styles.backLabel}>{offlineMode ? 'Reconnect' : 'Back'}</Text>
      </Pressable>
      {onOfflineScans ? <Button title="Saved scans" variant="quiet" icon="barcode-outline" onPress={onOfflineScans} /> : null}
      {count && (count.state === 'draft' || pending || offline.error) ? <CountSyncControl /> : count ? <Text style={styles.muted}>{countStates[count.state]}</Text> : null}
    </View>
    <Text accessibilityRole="header" style={styles.title}>Count</Text>
    <Text style={styles.muted}>{storeName}{count ? ` · ${count.businessDate}` : ''}</Text>
  </View>} footer={count ? <View style={[styles.footerSurface, { paddingBottom: footerInset }]}><View style={styles.footer}>
    <View style={styles.footerStatus}><Text style={styles.remaining}>{remaining ? `${remaining} left to count` : 'All products counted'}</Text></View>
    <Pressable accessibilityRole="button" accessibilityLabel={count.state === 'posted' ? 'View count comparison' : 'Review count'}
      accessibilityState={{ disabled: reviewDisabled }} disabled={reviewDisabled}
      onPress={review} style={({ pressed }) => [styles.review, (pressed || reviewDisabled) && styles.pressed]}>
      <Text style={styles.reviewText}>{count.state === 'posted' ? 'Compare' : 'Review'}</Text>
      <Ionicons name="arrow-forward" size={18} color={colors.onPrimary} />
    </Pressable>
  </View></View> : null}>
    {!allowed ? <Notice message="Your account does not have access to this count." kind="error" />
       : !count && offline.error ? <>
        <LoadError error={offline.error} refresh={() => controller.open(id)} />
        {offline.count && pending ? <Button title="Open saved count" onPress={() => nav.open({ pathname: '/counts/[countId]', params: { countId: offline.count!.id, ...countRouteParams(returnTo) } })} /> : null}
      </>
        : !count || offline.status === 'loading' ? <Loading label="Preparing count on this device…" />
          : <CountWorkspace count={count} />}
  </Screen>;
}

function CountWorkspace({ count }: { count: Count }) {
  const { canCount } = useCounts();
  const offline = useOfflineCount();
  const fontsReady = useFontsReady();
  const [filters, setFilters] = useRememberedState(`inventory.count.${count.id}.compactFilters`, {
    query: '', cursor: '', shelf: { id: '', name: 'All shelves' } as CountShelfChoice, missing: count.state === 'draft',
  });
  const [selected, setSelected] = useRememberedState<string | null>(`inventory.count.${count.id}.selectedLine`, null);
  const [query, setQuery] = useState(filters.query.trim());
  useEffect(() => {
    const timer = setTimeout(() => setQuery(filters.query.trim()), 250);
    return () => clearTimeout(timer);
  }, [filters.query]);
  const { cursor, shelf, missing } = filters;
  const choices = [...new Map(offline.lines.filter(line => line.shelfId).map(line => [line.shelfId!, { id: line.shelfId!, name: line.shelfName }])).values()]
    .sort((a, b) => a.name.localeCompare(b.name));
  const matching = offline.lines.filter(line => (!missing || line.quantity === null)
    && (!shelf.id || (shelf.id === 'unassigned' ? line.shelfId === null : line.shelfId === shelf.id))
    && (!query || `${line.name} ${line.sku}`.toLocaleLowerCase().includes(query.toLocaleLowerCase())));
  const offset = /^\d+$/.test(cursor) ? Number(cursor) : 0;
  const items = matching.slice(offset, offset + 40);
  const selectedLine = offline.lines.find(line => line.id === selected);
  const save = () => { setSelected(null); void offline.controller.sync().catch(() => undefined); };
  const chooseShelf = (choice: CountShelfChoice) => setFilters(value => ({ ...value, shelf: choice, cursor: '' }));
  return <View style={styles.workspace}>
    <View style={styles.context}>
      <CountShelfPicker value={shelf} onChange={chooseShelf} choices={choices} />
      <Text accessibilityLabel={`${count.countedProducts} of ${count.totalProducts} products counted`} style={styles.progressLabel}>
        {count.countedProducts}/{count.totalProducts} counted
      </Text>
    </View>
    <View accessibilityRole="progressbar" accessibilityLabel="Products counted"
      accessibilityValue={{ min: 0, max: count.totalProducts, now: count.countedProducts }} style={styles.track}>
      <View style={[styles.progress, { width: `${count.totalProducts ? count.countedProducts / count.totalProducts * 100 : 0}%` }]} />
    </View>
    {count.configurationChanged ? <Notice message={count.catalogProductsAvailable
      ? 'Connect to include the remaining catalog products.'
      : 'Products or shelves changed. An approver must restart this count before stock can be updated.'} kind="error" /> : null}
    <View style={styles.search}>
      <Ionicons name="search-outline" size={20} color={colors.muted} accessible={false} />
      <TextInput accessibilityLabel="Find a product" placeholder="Find a product" placeholderTextColor={colors.muted}
        selectionColor={colors.accentStrong} value={filters.query} maxLength={160} autoCorrect={false} returnKeyType="search"
        onChangeText={query => setFilters(value => ({ ...value, query, cursor: '' }))}
        onSubmitEditing={() => setQuery(filters.query.trim())}
        style={[styles.searchInput, { fontFamily: fontsReady ? fonts.body : undefined }]} />
      {filters.query ? <Pressable accessibilityRole="button" accessibilityLabel="Clear product search"
        onPress={() => { setQuery(''); setFilters(value => ({ ...value, query: '', cursor: '' })); }} style={styles.clear}>
        <Ionicons name="close-circle-outline" size={20} color={colors.muted} />
      </Pressable> : null}
    </View>
    <View style={styles.filters}>
      {[{ label: 'All', missing: false }, { label: 'Not counted', missing: true }].map(option =>
        <Pressable key={option.label} accessibilityRole="button" accessibilityLabel={option.label}
          accessibilityState={{ selected: missing === option.missing }}
          onPress={() => setFilters(value => ({ ...value, missing: option.missing, cursor: '' }))}
          style={({ pressed }) => [styles.filter, missing === option.missing && styles.filterSelected, pressed && styles.pressed]}>
          <Text style={[styles.filterLabel, missing === option.missing && styles.selectedLabel]}>{option.label}</Text>
        </Pressable>)}
    </View>
    <>
      {items.map(line => <CountRow key={line.id} line={line} showShelf={!shelf.id}
        editable={count.state === 'draft' && canCount && !count.configurationChanged} onPress={() => setSelected(line.id)} />)}
      {!items.length ? <View style={styles.empty}>
        <Body>{query ? 'No matching products.' : missing ? 'No uncounted products on this page.' : 'No products on this page.'}</Body>
        <Body muted>{cursor ? 'Return to the first page to check the rest.' : 'Choose All or another shelf to see more.'}</Body>
      </View> : null}
      <Pages next={offset + 40 < matching.length ? String(offset + 40) : null} cursor={cursor}
        setCursor={cursor => setFilters(value => ({ ...value, cursor }))} />
    </>
    {selectedLine ? <CountEntrySheet countId={count.id} lineId={selectedLine.id} onClose={() => setSelected(null)} onSaved={save}
      prepared={{ count, line: selectedLine, save: (line, entry) => offline.controller.save(line, entry) }} pending={offline.pendingLineIds.includes(selectedLine.id)} /> : null}
  </View>;
}

function CountRow({ line, showShelf, editable, onPress }: { line: CountLine; showShelf: boolean; editable: boolean; onPress: () => void }) {
  const packages = (line.packages || []).filter(item => item.active);
  const packageLabel = packages.length > 1 ? `${packages.length} package sizes`
    : packages.length === 1 ? `${packages[0]!.name} · ${quantityLabel(packages[0]!.amount, line.baseUnit)}`
      : line.containerAmount ? quantityLabel(line.containerAmount, line.baseUnit) : null;
  return <Pressable accessibilityRole="button" accessibilityLabel={`${editable ? 'Count' : 'View'} ${line.name} · ${line.shelfName}`}
    onPress={onPress} style={({ pressed }) => [styles.row, pressed && styles.rowPressed]}>
    <View style={styles.product}>
      <Text style={styles.productName}>{line.name}</Text>
      {showShelf || packageLabel ? <Text style={styles.productMeta}>{showShelf ? line.shelfName : packageLabel}</Text> : null}
    </View>
    <View style={styles.amount}>
      <Text style={[styles.quantity, line.quantity === null && styles.muted]}>{line.quantity === null ? 'Not counted' : quantityLabel(line.quantity, line.baseUnit)}</Text>
      <Ionicons name={line.quantity === null ? 'chevron-forward' : 'checkmark'} size={16}
        color={line.quantity === null ? colors.muted : colors.success} accessible={false} />
    </View>
  </Pressable>;
}

const styles = StyleSheet.create({
  header: { gap: 4, marginBottom: 4 }, headerTop: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 },
  back: { minHeight: 44, flexDirection: 'row', alignItems: 'center', gap: 6, paddingRight: 12 }, backLabel: { color: colors.primary, fontSize: 15 },
  title: { color: colors.ink, fontSize: 36, fontWeight: '500', fontFamily: fonts.display, marginVertical: 4 }, muted: { color: colors.muted, fontSize: 13 },
  workspace: { gap: 8 }, context: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 12 },
  progressLabel: { color: colors.muted, fontSize: 13, flexShrink: 0, fontVariant: ['tabular-nums'] },
  track: { height: 4, borderRadius: 2, backgroundColor: colors.soft, overflow: 'hidden', marginBottom: 8 }, progress: { height: 4, backgroundColor: colors.primary },
  search: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingLeft: 12, borderWidth: 1, borderColor: colors.controlLine, backgroundColor: colors.card, borderRadius: 12 },
  searchInput: { flex: 1, minWidth: 0, minHeight: 46, fontSize: 16, color: colors.ink, paddingVertical: 10, paddingRight: 12 }, clear: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center' },
  filters: { flexDirection: 'row', alignItems: 'center', gap: 6, flexWrap: 'wrap' }, filter: { minHeight: 44, paddingHorizontal: 14, paddingVertical: 10, borderRadius: 10, justifyContent: 'center' },
  filterSelected: { backgroundColor: colors.soft }, filterLabel: { fontSize: 14, color: colors.muted }, selectedLabel: { color: colors.ink, fontWeight: '600' },
  row: { minHeight: 62, flexDirection: 'row', alignItems: 'center', gap: 12, borderBottomWidth: 1, borderBottomColor: colors.line, paddingVertical: 10, paddingHorizontal: 2 },
  rowPressed: { backgroundColor: colors.soft }, product: { flex: 1, minWidth: 0 }, productName: { fontSize: 15, fontWeight: '600', color: colors.ink },
  productMeta: { fontSize: 12, color: colors.muted, marginTop: 3 }, amount: { flexDirection: 'row', alignItems: 'center', gap: 6, maxWidth: '46%', flexShrink: 0 },
  quantity: { fontSize: 14, color: colors.ink, textAlign: 'right', flexShrink: 1, fontVariant: ['tabular-nums'] },
  empty: { gap: 8, paddingVertical: 24 }, saved: { color: colors.success, fontSize: 13, paddingTop: 4 }, pressed: { opacity: 0.7 },
  footerSurface: { borderTopWidth: 1, borderTopColor: colors.line, backgroundColor: colors.card },
  footer: { width: '100%', maxWidth: 1120, alignSelf: 'center', paddingHorizontal: 22, paddingVertical: 14, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 },
  footerStatus: { flex: 1, gap: 3 }, remaining: { fontSize: 15, fontWeight: '600', color: colors.ink },
  review: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, minHeight: 48, paddingVertical: 12, paddingHorizontal: 18, borderRadius: 16, backgroundColor: colors.primary },
  reviewText: { color: colors.onPrimary, fontSize: 16, fontWeight: '600' },
});
