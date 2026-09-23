import { accountChangeUncertain } from './requests';
import React, { useState } from 'react';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Body, Button, Card, Column, Columns, EmptyState, Field, Heading, Notice, Pill } from '@/src/ui/components';
import { useSession } from '@/src/session/SessionProvider';
import { useTask } from '@/src/ui/useTask';
import { useSensitiveForm } from '@/src/ui/useSensitiveForm';
import { AdministrationScreen, Choice, confirmChange, Permissions, Reason, type AdminContext } from './AdminComponents';
import { accountId, accountState, type BusinessMember } from './types';

export function OwnerScreen() {
  return <AdministrationScreen title="A view of your business." ownerOnly>{context => <OwnerList {...context} />}</AdministrationScreen>;
}
function OwnerList({ data, changed }: AdminContext) {
  const router = useRouter();
  const { actor } = useSession();
  const [search, setSearch] = useState('');
  const people = data.directory.filter(member => `${member.displayName} ${member.username}`.toLowerCase().includes(search.toLowerCase()));
  return <><Columns><Column><Card><Heading>People & authority</Heading>
    <Body>Appoint administrators or additional owners, review account status, and transfer ownership. These controls apply to the business behind your selected store.</Body>
    <Button title="Manage this store's team" variant="secondary" icon="people-outline" onPress={() => router.push('/team')} />
  </Card></Column><Column><Card><Heading>Individual sign-in</Heading>
    <Pill label={data.sharedCrewEnabled ? 'Shared crew sign-in is enabled' : 'Individual crew sign-in only'} />
    <Body>Move this store to personal crew accounts when everyone has an active sign-in.</Body>
    <Button title="Review store sign-in" variant="secondary" icon="key-outline" onPress={() => router.push('/owner/cutover')} />
  </Card></Column></Columns>
  <Button title="Refresh business access" icon="refresh-outline" variant="quiet" onPress={() => { void changed('Business access refreshed.'); }} />
  <Field label="Find a person in this business" value={search} onChangeText={setSearch} autoCorrect={false} />
  {!people.length ? <Card><EmptyState title="No matching people" icon="people-outline" description="Try another name or invite someone through the store team." /></Card> : null}
  {people.map(person => <Card key={person.userId}><Heading>{person.displayName || person.username}{person.userId === actor?.userId ? ' (you)' : ''}</Heading>
    <Body muted>@{person.username} · {person.businessState === 'active' ? person.businessRole === 'owner' ? 'Business owner' : 'Delegated administrator' : 'Store memberships only'}</Body>
    <Pill label={accountState(person)} />
    {person.userId !== actor?.userId ? <Button title={`Review ${person.displayName || person.username}`} variant="secondary" onPress={() => router.push({ pathname: '/owner/[userId]', params: { userId: person.userId } })} />
      : <Body muted>To transfer your ownership, choose another active person below.</Body>}
  </Card>)}</>;
}
export function BusinessMemberScreen() {
  const { userId } = useLocalSearchParams<{ userId: string }>();
  return <AdministrationScreen title="Business authority." ownerOnly>{context => {
    const member = context.data.directory.find(person => person.userId === accountId(userId || ''));
    return member ? <BusinessMemberForm key={member.userId} {...context} member={member} />
      : <Card><Heading>Account unavailable</Heading><Body>Return to the owner workspace to select someone in this business.</Body></Card>;
  }}</AdministrationScreen>;
}
function BusinessMemberForm({ data, member, changed }: AdminContext & { member: BusinessMember }) {
  const { request, transferOwnership } = useSession();
  const task = useTask();
  const [role, setRole] = useState(member.businessRole || 'admin');
  const [grants, setGrants] = useState<string[]>(member.businessCapabilities);
  const [reason, setReason] = useState('');
  const [transferName, setTransferName] = useState('');
  useSensitiveForm(() => { setReason(''); setTransferName(''); setGrants([]); });
  const delegate = (active: boolean) => confirmChange(active ? `Update @${member.username}'s authority?` : `Remove @${member.username}'s business authority?`,
    `${active ? role === 'owner' ? 'An owner can manage the whole business and appoint other owners. Your ownership will remain.' : 'An administrator receives only the permissions you choose, intersected with their store access.' : 'Business authority will end; separate store memberships remain.'} Their sessions in this business will end.`,
    () => { void task.run(() => request('/accounts/business-memberships', { method: 'POST', uncertainMessage: accountChangeUncertain, body: {
      userId: member.userId, role: active ? role : member.businessRole, capabilities: active && role === 'admin' ? grants : [], active, reason,
    } }), () => { void changed(active ? 'Business authority saved. Review matching store access for administrators.' : 'Business authority removed.'); }); }, role === 'owner' || !active);
  const suspended = member.accountState !== 'suspended';
  const changeStatus = () => confirmChange(`${suspended ? 'Suspend' : 'Restore'} @${member.username}?`, suspended
    ? 'This suspends the entire account across every store and ends all sessions. Store membership records remain.'
    : 'Their active store memberships become available again. They can sign in with their existing password.', () => {
      void task.run(() => request('/accounts/suspend', { method: 'POST', uncertainMessage: accountChangeUncertain, body: { userId: member.userId, suspended, reason } }),
        () => { void changed(suspended ? 'Account suspended. All sessions have ended.' : 'Account restored. They can sign in again.'); });
    }, suspended);
  const transfer = () => confirmChange(`Transfer your ownership to @${member.username}?`,
    'Your ownership in this business will be removed and you will be signed out. The recipient will become a business owner. Their current sessions in this business will also end.',
    () => { void task.run(() => transferOwnership(member.userId, reason)); }, true);
  return <><Notice message={task.error} kind="error" /><Card><Heading>{member.displayName || member.username}</Heading>
    <Body muted>@{member.username} · Account ID {member.userId}</Body><Pill label={accountState(member)} />
    <Reason value={reason} onChange={setReason} disabled={task.pending} />
  </Card><Columns><Column><Card><Heading>Business role</Heading>
    {member.canDelegate ? <><Choice label="Administrator" hint="Explicit permissions, limited by store access" selected={role === 'admin'} disabled={task.pending} onPress={() => setRole('admin')} />
      <Choice label="Business owner" hint="Full authority across this business" selected={role === 'owner'} disabled={task.pending} onPress={() => setRole('owner')} />
      {role === 'admin' ? <><Permissions optional={data.businessCapabilities} value={grants} onChange={setGrants} disabled={task.pending} />
        <Body muted>For full administrator delegation at a store, also choose the Administrator store role and matching permissions in Team. A Store manager keeps that role; a shared-product delegation can add catalog access.</Body></> : null}
      <Button title="Save business authority" loading={task.pending} onPress={() => delegate(true)} />
    </> : <Body muted>Activate or restore this account before granting business authority. Your own authority is changed through ownership transfer.</Body>}
    {member.canRevokeBusiness ? <Button title="Remove business authority" variant="danger" disabled={task.pending} onPress={() => delegate(false)} /> : null}
  </Card></Column><Column><Card><Heading>Account status</Heading>
    {member.canSuspend ? <><Body>{suspended ? 'Suspend sign-in across every store this person belongs to.' : 'Restore this person’s ability to use their active memberships.'}</Body>
      <Button title={suspended ? 'Suspend account' : 'Restore account'} variant={suspended ? 'danger' : 'secondary'} disabled={task.pending} onPress={changeStatus} /></>
      : <Body muted>{member.accountState === 'pending' ? 'This account is awaiting activation. Manage or remove the invitation through its store membership.' : 'Account-wide suspension or restoration is unavailable with your current authority. Store access can still be managed separately where permitted.'}</Body>}
  </Card>
  {member.canTransfer ? <Card><Heading>Transfer your ownership</Heading><Body>You will give up your owner role in this business and be signed out. To keep your ownership, use Save business authority above instead.</Body>
    <Field label={`Type ${member.username} to confirm the recipient`} value={transferName} onChangeText={setTransferName} autoCapitalize="none" autoCorrect={false} editable={!task.pending} />
    <Button title="Transfer ownership" variant="danger" disabled={task.pending || transferName !== member.username} onPress={transfer} />
  </Card> : null}</Column></Columns></>;
}
export function CutoverScreen() {
  return <AdministrationScreen title="Personal sign-ins for everyone." ownerOnly>{context => <CutoverForm {...context} />}</AdministrationScreen>;
}
function CutoverForm({ data, storeName, changed }: AdminContext) {
  const { request } = useSession();
  const task = useTask();
  const [confirmation, setConfirmation] = useState('');
  const [reason, setReason] = useState('');
  useSensitiveForm(() => { setConfirmation(''); setReason(''); });
  const pending = data.members.filter(person => person.accountState === 'pending' && person.membershipState === 'active').length;
  const cutover = () => confirmChange(`Disable shared crew sign-in at ${storeName}?`,
    'Shared crew sessions at this store will end immediately. People must use individual accounts. This screen cannot turn shared sign-in back on.', () => {
      void task.run(() => request('/accounts/cutover', { method: 'POST', uncertainMessage: accountChangeUncertain, body: { storeId: data.storeId, reason } }),
        () => { void changed('Shared crew sign-in is disabled for this store.'); });
    }, true);
  return <><Notice message={task.error} kind="error" /><Card><Heading>{storeName}</Heading>
    {!data.sharedCrewEnabled ? <><Pill label="Individual crew sign-in only" /><Body>Shared crew sign-in is already disabled at this store. Personal accounts continue to work.</Body></>
      : <><Body>Confirm that everyone who works here has activated an individual account. Disabling shared sign-in ends shared crew sessions at this store immediately.</Body>
        <Notice message={pending ? `${pending} active store invitation${pending === 1 ? ' is' : 's are'} still awaiting activation.` : 'No active store invitations are awaiting activation. Confirm that your full crew has personal access.'} />
        <Field label="Type the store name to confirm" value={confirmation} onChangeText={setConfirmation} autoCorrect={false} editable={!task.pending} hint={storeName} />
        <Reason value={reason} onChange={setReason} disabled={task.pending} />
        <Button title="Disable shared crew sign-in" variant="danger" loading={task.pending} disabled={confirmation !== storeName} onPress={cutover} />
      </>}
  </Card></>;
}
