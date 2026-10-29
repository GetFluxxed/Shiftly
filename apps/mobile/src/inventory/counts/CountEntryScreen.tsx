import React, { useEffect } from 'react';
import { useLocalSearchParams, type Href } from 'expo-router';
import { Body, Loading, Notice } from '@/src/ui/components';
import { validId } from '../api';
import { InventoryPage, LoadError, useInventoryNavigation } from '../shared';
import { countBackTo, countRouteParams } from './shared';
import { useOfflineCount } from './OfflineCountsProvider';
import { CountEntrySheet } from './CountEntrySheet';

export function CountEntryScreen() {
  const { countId, lineId, returnTo } = useLocalSearchParams<{ countId: string; lineId: string; returnTo?: string }>();
  const nav = useInventoryNavigation();
  const queue = useOfflineCount();
  const { controller } = queue;
  useEffect(() => { if (validId(countId)) void controller.open(countId).catch(() => undefined); }, [controller, countId]);
  const count = queue.count?.id === countId ? queue.count : null;
  const line = count ? queue.lines.find(item => item.id === lineId) : null;
  const fallback = validId(countId)
    ? ({ pathname: '/counts/[countId]', params: { countId, ...countRouteParams(returnTo) } } as Href)
    : countBackTo(returnTo);
  const close = () => nav.back(fallback);
  return <InventoryPage title="Count entry" backTo={fallback} onBack={close}>
    {validId(countId) && validId(lineId) ? <>
      <Body muted>Select a product from the count to enter its quantity.</Body>
      {queue.error ? <LoadError error={queue.error} refresh={() => controller.open(countId)} />
        : !count || !line || queue.status === 'loading' ? <Loading label="Preparing count on this device…" />
        : <CountEntrySheet countId={countId} lineId={lineId} onClose={close}
          onSaved={() => { close(); void controller.sync().catch(() => undefined); }}
          prepared={{ count, line, save: (item, entry) => controller.save(item, entry) }}
          pending={queue.pendingLineIds.includes(lineId)} /> }
    </> : <Notice message="This entry is unavailable." kind="error" />}
  </InventoryPage>;
}
