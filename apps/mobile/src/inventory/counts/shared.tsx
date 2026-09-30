import React, { useCallback, useRef, useState } from 'react';
import { View } from 'react-native';
import { Body, Button, Card, Heading, Loading, Notice, Pill } from '@/src/ui/components';
import { useSession } from '@/src/session/SessionProvider';
import { useRememberedState } from '@/src/restoration/WorkspaceProvider';
import { MutationIdentity } from '../api';
import { useInventory, useInventoryResource, InventorySearch, LoadError, Pages } from '../shared';
import { countsApi, type Count } from './api';

export type CountReturnTo = string | string[] | undefined;
export function returnsToStock(returnTo: CountReturnTo) { return returnTo === 'stock'; }
export function countRouteParams(returnTo: CountReturnTo) { return returnsToStock(returnTo) ? { returnTo: 'stock' as const } : {}; }
export function countBackTo(returnTo: CountReturnTo): '/inventory' | '/stock' { return returnsToStock(returnTo) ? '/stock' : '/inventory'; }

export function useCounts() {
  const session = useSession(); const { request } = session;
  return { ...session, api: React.useMemo(() => countsApi(request), [request]), identity: useRef(new MutationIdentity()).current,
    canCount: !!session.actor?.capabilities.includes('counts.submit'), canApprove: !!session.actor?.capabilities.includes('counts.approve') };
}
export function CountHeading({ item }: { item: Count }) {
  return <Card><Heading>Count for {item.businessDate}</Heading><Pill label={{ draft: 'Counting in progress', review: 'Awaiting approval', posted: 'Finalized', cancelled: 'Cancelled' }[item.state]} />
    <Body>{item.countedLines} of {item.totalLines} locations counted · {item.totalProducts} products</Body><Body muted>Started by @{item.startedBy}</Body>
    {item.postedBy ? <Body muted>Finalized by @{item.postedBy}</Body> : null}
    {item.configurationChanged ? <Notice message="Products or shelves changed during this count. An approver must cancel it and start a fresh count before stock can be updated." kind="error" /> : null}
  </Card>;
}
export function Search({ onSearch, persistenceKey, label = 'Find a product or SKU' }: { onSearch: (value: string) => void; persistenceKey: string; label?: string }) {
  const [value, setValue] = useRememberedState(`${persistenceKey}.input`, '');
  return <InventorySearch label={label} value={value} onChange={setValue} submitLabel="Search inventory" onSubmit={() => onSearch(value.trim())} />;
}
export function ShelfFilter({ value, onChange, persistenceKey }: { value: string; onChange: (value: string) => void; persistenceKey: string }) {
  const { api } = useInventory(); const [open, setOpen] = useState(false), [cursor, setCursor] = useRememberedState(`${persistenceKey}.cursor`, '');
  const resource = useInventoryResource(useCallback(() => api.shelves(cursor), [api, cursor]), open);
  const choose = (id: string) => { onChange(id); setOpen(false); };
  return <><Button title={`Shelf filter: ${value ? value === 'unassigned' ? 'Unassigned products' : 'Selected shelf' : 'All shelves'}`} variant="quiet" onPress={() => setOpen(!open)} />
    {open ? <Card><Heading>Choose a shelf</Heading><Button title="All shelves" variant="secondary" onPress={() => choose('')} />
      <Button title="Unassigned products" variant="secondary" onPress={() => choose('unassigned')} />
      {resource.loading ? <Loading label="Loading shelves…" /> : resource.error || !resource.data ? <LoadError {...resource} /> : <>
        {resource.data.items.map(s => <Button key={s.id} title={s.name} variant="secondary" onPress={() => choose(s.id)} />)}
        <Pages next={resource.data.nextCursor} cursor={cursor} setCursor={setCursor} />
      </>}
    </Card> : null}</>;
}
export function UnitButtons({ value, base, onChange, disabled }: { value: string; base: string; onChange: (unit: 'g' | 'kg' | 'each') => void; disabled: boolean }) {
  return <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>{(base === 'each' ? ['each'] as const : ['g', 'kg'] as const).map(unit =>
    <Button key={unit} title={unit === 'each' ? 'Items' : unit === 'g' ? 'Grams' : 'Kilograms'} variant={unit === value ? 'primary' : 'secondary'} disabled={disabled} onPress={() => onChange(unit)} />)}</View>;
}
