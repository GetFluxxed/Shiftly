import React, { useState } from 'react';
import { usePathname } from 'expo-router';
import { useSession } from '../session/SessionProvider';
import { CountWorkspaceScreen } from './counts/CountWorkspaceScreen';
import { SavedScansScreen } from './scans/SavedScansScreen';

/** Deliberately exposes only explicitly prepared offline work, never the full tabs. */
export function OfflineInventoryWorkspace() {
  const { offlineCountId, offlineCatalogCapture } = useSession();
  const pathname = usePathname();
  const [scans, setScans] = useState(pathname.startsWith('/catalog/'));
  if (offlineCatalogCapture && (scans || !offlineCountId)) return <SavedScansScreen offlineMode
    onBack={offlineCountId ? () => setScans(false) : undefined} />;
  if (offlineCountId) return <CountWorkspaceScreen id={offlineCountId} offlineMode
    onOfflineScans={offlineCatalogCapture ? () => setScans(true) : undefined} />;
  return null;
}
