import type { SessionController } from '../../session/controller';
import type { SavedScansController } from './controller';
import { sameScanOwner, type ScanOwner } from './model';

export function scanOwnerFor(session: Pick<SessionController, 'getSnapshot' | 'canCaptureScans'>): ScanOwner | null {
  const { actor } = session.getSnapshot();
  return actor?.businessId && session.canCaptureScans()
    ? { userId: actor.userId, businessId: actor.businessId, storeId: actor.storeId } : null;
}

/** Never grant offline access until the durable inbox is readable in this scope. */
export async function prepareSavedScans(session: Pick<SessionController,
  'getSnapshot' | 'canCaptureScans' | 'authorizeOfflineCatalogCapture'>,
  controller: Pick<SavedScansController, 'getSnapshot' | 'activate'>): Promise<void> {
  const owner = scanOwnerFor(session), revision = session.getSnapshot().revision;
  if (!owner) throw new Error('Catalog management access is required.');
  const state = controller.getSnapshot();
  if (state.status !== 'ready' || !state.owner || !sameScanOwner(owner, state.owner)) await controller.activate(owner);
  const current = scanOwnerFor(session), loaded = controller.getSnapshot();
  if (!current || !sameScanOwner(owner, current) || revision !== session.getSnapshot().revision)
    throw new Error('Your account or store changed.');
  if (loaded.status !== 'ready' || !loaded.owner || !sameScanOwner(owner, loaded.owner))
    throw new Error('Saved scans could not be restored. Keep this device until the saved work is recovered.');
  // An existing offline grant can reopen a recovered inbox, but cannot renew itself.
  if (session.getSnapshot().status === 'ready') await session.authorizeOfflineCatalogCapture();
}
