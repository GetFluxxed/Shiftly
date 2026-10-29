import { accountChangeUncertain } from './requests';
import React, { useState } from 'react';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Body, Button, Card, Column, Columns, EmptyState, Field, Heading, Notice, Pill } from '@/src/ui/components';
import { useSession } from '@/src/session/SessionProvider';
import { useTask } from '@/src/ui/useTask';
import { useSensitiveForm } from '@/src/ui/useSensitiveForm';
import { AdministrationScreen, Choice, confirmChange, Permissions, Reason, type AdminContext } from './AdminComponents';
import { accountId, accountState, type BusinessMember } from './types';
import { useRememberedState } from '@/src/restoration/WorkspaceProvider';

export function OwnerScreen() {
  return <AdministrationScreen title="Owner tools" ownerOnly>{context => <OwnerList {...context} />}</AdministrationScreen>;
}
function OwnerList({ data, changed }: AdminContext) {
  const router = useRouter();
  const { actor } = useSession();
  const [search, setSearch] = useRememberedState('owner.people.search', '');
  const people = data.directory.filter(member => `${member.displayName} ${member.username}`.toLowerCase().includes(search.toLowerCase()));
  return <><Columns><Column><Card><Heading>People & authority</Heading>
    <Body>Manage administrators, owners, account status, and ownership.</Body>
    <Button title="Manage this store's team" variant="secondary" icon="people-outline" onPress={() => router.push('/team')} />
  </Card></Column><Column><Card><Heading>Individual sign-in</Heading>
    <Pill label="Individual sign-in required" />
    <Body>Everyone joins by invitation and uses their own username and password.</Body>
    <Button title="Review store sign-in" variant="secondary" icon="key-outline" onPress={() => router.push('/owner/cutover')} />
  </Card></Column></Columns>
    <Button title="Refresh owner access" icon="refresh-outline" variant="quiet" onPress={() => { void changed('Owner access refreshed.'); }} />
  <Field label="Find a person" value={search} onChangeText={setSearch} autoCorrect={false} />
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
  return <AdministrationScreen title="Business access" ownerOnly>{context => {
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
  const delegate = (active: boolean) => confirmChange(active ? `Update @${member.username}'s business access?` : `Remove @${member.username}'s business access?`,
    `${active ? role === 'owner' ? 'An owner can manage the whole business and appoint other owners. Your ownership will remain.' : 'An administrator receives only the permissions you choose, limited by their store access.' : 'Business access will end; store access remains.'} Their sessions in this business will end.`,
    () => { void task.run(() => request('/accounts/business-memberships', { method: 'POST', uncertainMessage: accountChangeUncertain, body: {
      userId: member.userId, role: active ? role : member.businessRole, capabilities: active && role === 'admin' ? grants : [], active, reason,
    } }), () => { void changed(active ? 'Business access saved. Check matching store access for administrators.' : 'Business access removed.'); }); }, role === 'owner' || !active);
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
    {member.canDelegate ? <><Choice label="Administrator" hint="Selected permissions, limited by store access" selected={role === 'admin'} disabled={task.pending} onPress={() => setRole('admin')} />
      <Choice label="Business owner" hint="Full access across this business" selected={role === 'owner'} disabled={task.pending} onPress={() => setRole('owner')} />
      {role === 'admin' ? <><Permissions optional={data.businessCapabilities} value={grants} onChange={setGrants} disabled={task.pending} />
        <Body muted>For full store access, also assign the Administrator role and matching permissions in Team.</Body></> : null}
      <Button title="Save business access" loading={task.pending} onPress={() => delegate(true)} />
    </> : <Body muted>Activate or restore this account first. Transfer ownership to change your own access.</Body>}
    {member.canRevokeBusiness ? <Button title="Remove business access" variant="danger" disabled={task.pending} onPress={() => delegate(false)} /> : null}
  </Card></Column><Column><Card><Heading>Account status</Heading>
    {member.canSuspend ? <><Body>{suspended ? 'Suspend sign-in across every store this person belongs to.' : 'Restore this person’s ability to use their active memberships.'}</Body>
      <Button title={suspended ? 'Suspend account' : 'Restore account'} variant={suspended ? 'danger' : 'secondary'} disabled={task.pending} onPress={changeStatus} /></>
      : <Body muted>{member.accountState === 'pending' ? 'Awaiting activation. Manage the invitation from Team.' : 'You cannot change this account status. Store access may still be available in Team.'}</Body>}
  </Card>
  {member.canTransfer ? <Card><Heading>Transfer ownership</Heading><Body>You will lose owner access and be signed out.</Body>
    <Field label={`Type ${member.username} to confirm the recipient`} value={transferName} onChangeText={setTransferName} autoCapitalize="none" autoCorrect={false} editable={!task.pending} />
    <Button title="Transfer ownership" variant="danger" disabled={task.pending || transferName !== member.username} onPress={transfer} />
  </Card> : null}</Column></Columns></>;
}
export function CutoverScreen() {
  return <AdministrationScreen title="Store sign-in" ownerOnly>{context => <CutoverForm {...context} />}</AdministrationScreen>;
}
function CutoverForm({ storeName }: AdminContext) {
  return <Card><Heading>{storeName}</Heading><Pill label="Individual sign-in required" />
    <Body>New people join with a single-use invitation. Crew and managers have one store. Administrators set roles and permissions after activation.</Body></Card>;
}
