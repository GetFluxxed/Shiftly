import { accountChangeUncertain } from './requests';
import React, { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, View } from 'react-native';
import Ionicons from '@expo/vector-icons/Ionicons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Text } from '@/src/ui/Typography';
import { ActionGrid, ActionTile } from '@/src/ui/ActionGrid';
import { Body, Button, Card, Column, Columns, EmptyState, Field, Heading, Notice, Pill, layout } from '@/src/ui/components';
import { colors, friendlyDate, roleLabels } from '@/src/ui/theme';
import { useSession } from '@/src/session/SessionProvider';
import { useTask } from '@/src/ui/useTask';
import { useSensitiveForm } from '@/src/ui/useSensitiveForm';
import { AdministrationScreen, confirmChange, InvitationResult, Permissions, Reason, Roles, type AdminContext } from './AdminComponents';
import { accountId, accountState, roleGrants, type Invitation, type TeamMember } from './types';
import { useRememberedState } from '@/src/restoration/WorkspaceProvider';

function memberName(member: TeamMember) {
  return member.displayName || member.username;
}

export function TeamScreen() {
  return <AdministrationScreen title="Team members.">{context => <TeamMemberSelector {...context} />}</AdministrationScreen>;
}

function TeamMemberSelector({ data, changed }: AdminContext) {
  const router = useRouter();
  const { actor } = useSession();
  const [expanded, setExpanded] = useRememberedState('team.selector.expanded', false);
  const [search, setSearch] = useRememberedState('team.selector.search', '');
  const [selectedId, setSelectedId] = useRememberedState<number | null>('team.selector.selected', null);
  const members = data.members;
  const matching = members.filter(member => `${member.displayName} ${member.username}`.toLowerCase().includes(search.trim().toLowerCase()));
  const selected = members.find(member => member.userId === selectedId) || null;
  const select = (member: TeamMember) => {
    setSelectedId(member.userId);
    setExpanded(false);
    setSearch('');
  };

  return <View style={layout.gap}>
    {actor?.capabilities.includes('memberships.manage') ? <Button title="Build your team" icon="person-add-outline" variant="secondary"
      onPress={() => router.push('/team/build')} /> : null}
    <Button title="Refresh team" icon="refresh-outline" variant="quiet" onPress={() => { void changed('Team refreshed.'); }} />
    {!members.length ? <Card><EmptyState icon="people-outline" title="Your team starts here"
      description="Build your team to invite a new person or add an existing account to this store." /></Card> : <>
      <View style={styles.selector}>
        <Body muted>Most recent sign-ins first.</Body>
        <Pressable accessibilityRole="button" accessibilityLabel={selected ? `Selected team member: ${memberName(selected)}` : 'Choose a team member'}
          accessibilityState={{ expanded }} onPress={() => setExpanded(value => !value)}
          style={({ pressed }) => [styles.selectorButton, pressed && styles.pressed]}>
          <View style={layout.flex}>
            <Text style={styles.selectorLabel}>Team member</Text>
            <Text style={styles.selectorValue}>{selected ? memberName(selected) : 'Choose a person'}</Text>
          </View>
          <Ionicons name={expanded ? 'chevron-up' : 'chevron-down'} size={20} color={colors.primary} accessible={false} />
        </Pressable>
        {expanded ? <View style={styles.menu}>
          <Field label="Find a team member" value={search} onChangeText={setSearch} autoCorrect={false} autoCapitalize="none" />
          <ScrollView style={styles.memberList} contentContainerStyle={styles.memberListContent} nestedScrollEnabled
            keyboardShouldPersistTaps="handled" accessibilityLabel="Team member choices">
            {!matching.length ? <Body muted>No matching people.</Body> : matching.map(member =>
              <Pressable key={member.userId} accessibilityRole="button" accessibilityLabel={`Choose ${memberName(member)}`}
                onPress={() => select(member)} style={({ pressed }) => [styles.memberChoice, pressed && styles.pressed]}>
                <View style={layout.flex}><Text style={styles.memberName}>{memberName(member)}</Text><Text style={styles.memberMeta}>@{member.username}</Text></View>
                <Ionicons name="chevron-forward" size={18} color={colors.muted} accessible={false} />
              </Pressable>)}
          </ScrollView>
        </View> : null}
      </View>
      {selected ? <Card>
        <Heading>{memberName(selected)}</Heading>
        <Body muted>@{selected.username} · {selected.businessRole === 'owner' && selected.businessState === 'active' ? 'Business owner' : roleLabels[selected.role]}</Body>
        <View style={layout.wrap}><Pill label={accountState(selected, selected.membershipState)} /></View>
        <Body muted>{selected.lastSignInAt ? `Last signed in here ${friendlyDate(selected.lastSignInAt)}` : 'No sign-in recorded here'}</Body>
        {selected.canEdit ? <Button title={`Manage ${memberName(selected)}`} variant="secondary"
          onPress={() => router.push({ pathname: '/team/[userId]', params: { userId: selected.userId } })} />
          : <Body muted>View only with your current account.</Body>}
      </Card> : <Notice message="Choose a team member to view their store access." />}
    </>}
  </View>;
}

export function BuildTeamScreen() {
  return <AdministrationScreen title="Build your team.">{context => <BuildTeamActions {...context} />}</AdministrationScreen>;
}

function BuildTeamActions({ data }: AdminContext) {
  const router = useRouter();
  const { actor } = useSession();
  const canInvite = data.roles.some(choice => choice.role === 'crew');
  const canAssignRole = ['owner', 'admin'].includes(actor?.role || '');
  const canAssignExisting = Boolean(data.roles.length && canAssignRole);
  const assignmentRestriction = canAssignRole ? 'Account assignment permission required' : 'Administrator or owner only';
  return <><ActionGrid>
    <ActionTile title="Invite a New Person" label={canInvite ? 'Invite a new person' : 'Invite a new person. Invitation permission required.'}
      icon="person-add-outline" disabled={!canInvite} onPress={() => router.push('/team/invite')}
      footer={!canInvite ? <Text style={styles.tileFooter}>Invitation unavailable</Text> : undefined} />
    <ActionTile title="Add an Existing Account" label={canAssignExisting ? 'Add an existing account' : `Add an existing account. ${assignmentRestriction}.`}
      icon="person-add-outline" disabled={!canAssignExisting} onPress={() => router.push('/team/assign')}
      footer={!canAssignExisting ? <Text style={styles.tileFooter}>{assignmentRestriction}</Text> : undefined} />
  </ActionGrid></>;
}

export function InviteScreen() {
  return <AdministrationScreen title="Welcome someone new.">{context => <InviteForm {...context} />}</AdministrationScreen>;
}
function InviteForm({ data, storeName }: AdminContext) {
  const { request } = useSession();
  const router = useRouter();
  const task = useTask();
  const choices = data.roles.filter(choice => choice.role === 'crew');
  const [username, setUsername] = useState('');
  const [name, setName] = useState('');
  const role = 'crew';
  const [reason, setReason] = useState('');
  const [invitation, setInvitation] = useState<Invitation | null>(null);
  useSensitiveForm(() => { setInvitation(null); setUsername(''); setName(''); setReason(''); });
  const choice = choices.find(item => item.role === role);
  const submit = () => confirmChange(`Invite @${username.trim()}?`, `${roleLabels[role]} access at ${storeName}. The invitation expires in 24 hours.`, () => {
    void task.run(() => request<Invitation>('/accounts/invitations', { method: 'POST', uncertainMessage: accountChangeUncertain, body: {
      username: username.trim(), displayName: name.trim(), role: 'crew', capabilities: [], storeId: data.storeId, expiresIn: 86400, reason,
    } }), setInvitation);
  });
  if (invitation) return <InvitationResult invitation={invitation} username={username.trim()} onDismiss={() => { setInvitation(null); router.replace('/team'); }} />;
  return <><Notice message={task.error} kind="error" /><Columns><Column><Card>
    <Heading>Personal sign-in</Heading><Body>They will set their own password when they activate the invitation.</Body>
    <Field label="Username" value={username} onChangeText={setUsername} autoCapitalize="none" autoCorrect={false} maxLength={80} editable={!task.pending} />
    <Field label="Display name" value={name} onChangeText={setName} maxLength={120} editable={!task.pending} />
    <Reason value={reason} onChange={setReason} disabled={task.pending} />
  </Card></Column><Column><Card><Heading>Crew first</Heading>
    <Body>Every invitation creates an individual crew account at this store. After activation, an authorized administrator or owner can assign Production access or change their permissions.</Body>
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
  const choices = data.roles.filter(choice => (member?.accountState !== 'pending' || choice.role === 'crew') && (choice.role !== 'admin' || !member || (member.businessRole === 'admin' && member.businessState === 'active')));
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
      : <><Body>Ask the person for their Account ID, shown on their Account screen. Their password stays the same. Crew, Production, and managers can belong to one store. An administrator must remove their previous store membership before a transfer.</Body>
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
    {choice && member?.accountState !== 'pending' ? <Permissions included={choice.included} optional={choice.optional} value={grants} onChange={setGrants} disabled={task.pending} /> : null}
    <Button title={member?.membershipState === 'revoked' ? 'Restore store access' : 'Save store access'} loading={task.pending}
      disabled={!userId || userId === actor?.userId || !choice} onPress={() => save(true)} />
    {member?.membershipState === 'active' ? <Button title="Remove store access" variant="danger" disabled={task.pending || !choice} onPress={() => save(false)} /> : null}
  </Card></Column></Columns></>;
}

const styles = StyleSheet.create({
  selector: { gap: 10 },
  selectorButton: { minHeight: 64, borderWidth: 1, borderColor: colors.controlLine, borderRadius: 14, backgroundColor: colors.white,
    paddingHorizontal: 16, paddingVertical: 12, flexDirection: 'row', alignItems: 'center', gap: 12 },
  selectorLabel: { color: colors.muted, fontSize: 12, lineHeight: 17, fontWeight: '600', textTransform: 'uppercase', letterSpacing: 0.6 },
  selectorValue: { color: colors.ink, fontSize: 17, lineHeight: 24, fontWeight: '600' },
  menu: { gap: 12, borderWidth: 1, borderColor: colors.line, borderRadius: 16, backgroundColor: colors.card, padding: 14 },
  memberList: { maxHeight: 300 }, memberListContent: { gap: 6 },
  memberChoice: { minHeight: 58, paddingVertical: 10, paddingHorizontal: 12, borderRadius: 12, flexDirection: 'row', alignItems: 'center', gap: 10 },
  memberName: { color: colors.ink, fontSize: 16, lineHeight: 22, fontWeight: '600' },
  memberMeta: { color: colors.muted, fontSize: 13, lineHeight: 19 },
  tileFooter: { color: colors.muted, fontSize: 13, lineHeight: 18, paddingHorizontal: 12, paddingBottom: 12 },
  pressed: { backgroundColor: colors.blush },
});
