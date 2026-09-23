import { accountChangeUncertain } from './requests';
import React, { useState } from 'react';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Body, Button, Card, Column, Columns, EmptyState, Field, Heading, Notice, Pill } from '@/src/ui/components';
import { roleLabels } from '@/src/ui/theme';
import { useSession } from '@/src/session/SessionProvider';
import { useTask } from '@/src/ui/useTask';
import { useSensitiveForm } from '@/src/ui/useSensitiveForm';
import { AdministrationScreen, confirmChange, InvitationResult, Permissions, Reason, Roles, type AdminContext } from './AdminComponents';
import { accountId, accountState, roleGrants, type Invitation, type TeamMember } from './types';

export function TeamScreen() {
  return <AdministrationScreen title="Your people.">{context => <TeamList {...context} />}</AdministrationScreen>;
}
function TeamList({ data, changed }: AdminContext) {
  const router = useRouter();
  const [search, setSearch] = useState('');
  const members = data.members.filter(member => `${member.displayName} ${member.username}`.toLowerCase().includes(search.toLowerCase()));
  return <><Columns><Column><Card><Heading>Build your team</Heading><Body>Give each person their own sign-in and the access they need at this store.</Body>
    <Button title="Invite a new person" icon="person-add-outline" disabled={!data.roles.some(role => role.role !== 'admin')} onPress={() => router.push('/team/invite')} />
    <Button title="Add an existing account" variant="secondary" disabled={!data.roles.length} onPress={() => router.push('/team/assign')} />
  </Card></Column><Column><Card><Heading>Store access</Heading><Body>Changing a membership ends that person's current sessions at this store. Business owners retain access through their business role.</Body>
    {data.isOwner ? <Button title="Open owner workspace" variant="secondary" icon="shield-checkmark-outline" onPress={() => router.push('/owner')} /> : null}
  </Card></Column></Columns>
  <Button title="Refresh team" icon="refresh-outline" variant="quiet" onPress={() => { void changed('Team refreshed.'); }} />
  <Field label="Find a team member" value={search} onChangeText={setSearch} autoCorrect={false} />
  {!members.length ? <Card><EmptyState icon="people-outline" title={search ? 'No matching people' : 'Your team starts here'} description="Invite a new person or add an existing account to this store." /></Card> : null}
  {members.map(member => <Card key={member.userId}><Heading>{member.displayName || member.username}</Heading>
    <Body muted>@{member.username} · {member.businessRole === 'owner' && member.businessState === 'active' ? 'Business owner' : roleLabels[member.role]}</Body>
    <Pill label={accountState(member, member.membershipState)} />
    {member.canEdit ? <Button title={`Manage ${member.displayName || member.username}`} variant="secondary" onPress={() => router.push({ pathname: '/team/[userId]', params: { userId: member.userId } })} />
      : <Body muted>View only with your current account.</Body>}
  </Card>)}</>;
}
export function InviteScreen() {
  return <AdministrationScreen title="Welcome someone new.">{context => <InviteForm {...context} />}</AdministrationScreen>;
}
function InviteForm({ data, storeName }: AdminContext) {
  const { request } = useSession();
  const router = useRouter();
  const task = useTask();
  const choices = data.roles.filter(choice => choice.role !== 'admin');
  const [username, setUsername] = useState('');
  const [name, setName] = useState('');
  const [role, setRole] = useState(choices[0]?.role || '');
  const [grants, setGrants] = useState<string[]>([]);
  const [reason, setReason] = useState('');
  const [invitation, setInvitation] = useState<Invitation | null>(null);
  useSensitiveForm(() => { setInvitation(null); setUsername(''); setName(''); setReason(''); setGrants([]); });
  const choice = choices.find(item => item.role === role);
  const submit = () => confirmChange(`Invite @${username.trim()}?`, `${roleLabels[role]} access at ${storeName}. The invitation expires in 24 hours.`, () => {
    void task.run(() => request<Invitation>('/accounts/invitations', { method: 'POST', uncertainMessage: accountChangeUncertain, body: {
      username: username.trim(), displayName: name.trim(), role, capabilities: grants, storeId: data.storeId, expiresIn: 86400, reason,
    } }), setInvitation);
  });
  if (invitation) return <InvitationResult invitation={invitation} username={username.trim()} onDismiss={() => { setInvitation(null); router.replace('/team'); }} />;
  return <><Notice message={task.error} kind="error" /><Columns><Column><Card>
    <Heading>Personal sign-in</Heading><Body>They will set their own password when they activate the invitation.</Body>
    <Field label="Username" value={username} onChangeText={setUsername} autoCapitalize="none" autoCorrect={false} maxLength={80} editable={!task.pending} />
    <Field label="Display name" value={name} onChangeText={setName} maxLength={120} editable={!task.pending} />
    <Reason value={reason} onChange={setReason} disabled={task.pending} />
  </Card></Column><Column><Card><Roles choices={choices} value={role} disabled={task.pending} onChange={value => { setRole(value); setGrants([]); }} />
    {choice ? <Permissions included={choice.included} optional={choice.optional} value={grants} onChange={setGrants} disabled={task.pending} /> : null}
    <Button title="Create invitation" loading={task.pending} disabled={!username.trim() || !choice} onPress={submit} />
  </Card></Column></Columns></>;
}
export function AssignScreen() {
  return <AdministrationScreen title="Connect an existing account.">{context => <MembershipForm {...context} />}</AdministrationScreen>;
}
export function MemberScreen() {
  const { userId } = useLocalSearchParams<{ userId: string }>();
  return <AdministrationScreen title="Team member access.">{context => {
    const member = context.data.members.find(item => item.userId === accountId(userId || ''));
    return member?.canEdit ? <MembershipForm key={member.userId} {...context} member={member} />
      : <Card><Heading>This membership is unavailable</Heading><Body>Return to the team to see the people you can manage.</Body></Card>;
  }}</AdministrationScreen>;
}
function MembershipForm({ data, storeName, changed, member }: AdminContext & { member?: TeamMember }) {
  const { request, actor } = useSession();
  const task = useTask();
  const [user, setUser] = useState(member ? String(member.userId) : '');
  const [role, setRole] = useState(member?.role || data.roles[0]?.role || '');
  const [grants, setGrants] = useState<string[]>(member?.capabilities || []);
  const [reason, setReason] = useState('');
  const [invitation, setInvitation] = useState<Invitation | null>(null);
  useSensitiveForm(() => { setInvitation(null); setReason(''); setUser(''); setGrants([]); });
  const choices = data.roles.filter(choice => choice.role !== 'admin' || !member || (member.businessRole === 'admin' && member.businessState === 'active'));
  const choice = choices.find(item => item.role === role);
  const userId = member?.userId ?? accountId(user);
  const name = member ? `@${member.username}` : `account ${userId}`;
  const save = (active: boolean) => confirmChange(active ? `Save access for ${name}?` : `Remove ${name} from this store?`,
    `${active ? `${roleLabels[role]} access will be assigned at` : 'Store membership will be removed at'} ${storeName}. Their sessions at this store will end.${member?.accountState === 'pending' ? ' Any existing activation code will stop working; reissue an invitation after saving.' : ''}${member?.businessRole === 'owner' && member.businessState === 'active' ? ' Business owner access will remain.' : ''}`,
    () => { void task.run(async () => {
      await request('/accounts/memberships', { method: 'POST', uncertainMessage: accountChangeUncertain, body: { userId, role, capabilities: grants, active, storeId: data.storeId, reason } });
    }, () => { void changed(active ? 'Store access saved. Existing sessions at this store have ended.' : 'Store membership removed.'); }); }, !active);
  const reissue = () => confirmChange(`Replace the invitation for ${name}?`, 'Any earlier activation code will stop working. The new code expires in 24 hours.', () => {
    void task.run(() => request<Invitation>('/accounts/invitations/reissue', { method: 'POST', uncertainMessage: accountChangeUncertain, body: { userId, storeId: data.storeId, expiresIn: 86400, reason } }), setInvitation);
  });
  if (invitation) return <InvitationResult invitation={invitation} username={member?.username || name} onDismiss={() => { setInvitation(null); void changed('Invitation issued.'); }} />;
  return <><Notice message={task.error} kind="error" /><Columns><Column><Card>
    <Heading>{member?.displayName || 'An account they already use'}</Heading>
    {member ? <><Body muted>@{member.username} · Account ID {member.userId}</Body><Pill label={accountState(member, member.membershipState)} /></>
      : <><Body>Ask the person for their Account ID, shown on their Account screen. Their password stays the same. Activate pending invitations before adding another store.</Body>
        <Field label="Account ID" value={user} onChangeText={setUser} keyboardType="number-pad" maxLength={16} editable={!task.pending} />
        {data.isOwner && data.directory.filter(person => person.userId !== actor?.userId && person.accountState === 'active' && !data.members.some(item => item.userId === person.userId)).map(person =>
          <Button key={person.userId} title={`Choose ${person.displayName} (@${person.username})`} variant="secondary" disabled={task.pending} onPress={() => setUser(String(person.userId))} />)}
      </>}
    <Reason value={reason} onChange={setReason} disabled={task.pending} />
    {member?.canReissue ? <Button title="Reissue activation code" variant="secondary" disabled={task.pending} onPress={reissue} /> : null}
    {member?.accountState === 'pending' && !member.canReissue ? <Body muted>An invitation can be reissued only for a permitted, active membership with a single store assignment.</Body> : null}
  </Card></Column><Column><Card><Roles choices={choices} value={role} disabled={task.pending} onChange={value => {
    setRole(value); setGrants(roleGrants(choices.find(item => item.role === value), grants));
  }} />
    {role === 'admin' ? <Body muted>Administrator access also requires an active business delegation with matching permissions. An owner sets that in the owner workspace.</Body> : null}
    {choice ? <Permissions included={choice.included} optional={choice.optional} value={grants} onChange={setGrants} disabled={task.pending} /> : null}
    <Button title={member?.membershipState === 'revoked' ? 'Restore store access' : 'Save store access'} loading={task.pending}
      disabled={!userId || userId === actor?.userId || !choice} onPress={() => save(true)} />
    {member?.membershipState === 'active' ? <Button title="Remove store access" variant="danger" disabled={task.pending || !choice} onPress={() => save(false)} /> : null}
  </Card></Column></Columns></>;
}
