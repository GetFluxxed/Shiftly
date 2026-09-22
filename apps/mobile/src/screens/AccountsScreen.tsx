import React, { useRef, useState } from 'react';
import { Alert, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import Ionicons from '@expo/vector-icons/Ionicons';
import { useSession } from '@/src/session/SessionProvider';
import { Body, Button, Card, Column, Columns, EmptyState, Field, Heading, Loading, Notice, Pill, Screen, layout } from '@/src/ui/components';
import { colors, permissionLabels, roleLabels } from '@/src/ui/theme';
import { useTask } from '@/src/ui/useTask';
import { useResource } from '@/src/ui/useResource';
import { useSensitiveForm } from '@/src/ui/useSensitiveForm';

type TeamMember = {
  userId: number; username: string; displayName: string; accountState: string; role: string;
  membershipState: string; capabilities: string[];
  businessRole?: string | null; businessState?: string | null; businessCapabilities?: string[];
};

export function AccountsScreen() {
  const { actor, stores, switchStore, changePassword, signOut, busy } = useSession();
  const task = useTask();
  const [choosingStore, setChoosingStore] = useState(false);
  const [changingPassword, setChangingPassword] = useState(false);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [notice, setNotice] = useState<string | null>(null);
  const newPasswordInput = useRef<TextInput>(null);
  const confirmationInput = useRef<TextInput>(null);
  useSensitiveForm(() => { setCurrentPassword(''); setNewPassword(''); setConfirmation(''); setChangingPassword(false); });
  const store = stores.find((item) => item.storeId === actor?.storeId);
  const name = actor?.displayName || actor?.username || 'Your account';
  const initials = name.split(' ').slice(0, 2).map((part) => part[0]).join('').toUpperCase();
  const chooseStore = (storeId: number, storeName: string) => {
    if (storeId === actor?.storeId) { setChoosingStore(false); return; }
    Alert.alert(`Switch to ${storeName}?`, 'Your workspace will reload for this store. Unsent notes will be cleared.', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Switch store', onPress: () => { void task.run(() => switchStore(storeId)); } },
    ]);
  };
  const savePassword = () => {
    if (newPassword !== confirmation) { task.setError('Your new passwords do not match.'); return; }
    void task.run(async () => {
      const previous = currentPassword; const next = newPassword;
      setCurrentPassword(''); setNewPassword(''); setConfirmation('');
      await changePassword(previous, next);
    }, () => { setChangingPassword(false); setNotice('Your password was changed.'); });
  };
  const signOutEverywhere = () => Alert.alert('Sign out on every device?',
    'All sessions for your account will end, including this one. You can sign in again with your password.', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Sign out everywhere', style: 'destructive', onPress: () => { void task.run(() => signOut(true)); } },
    ]);
  return <Screen title="Your account. Your space." eyebrow="Account & access"
    subtitle="Manage your sign-in and see how you're connected to your team.">
    <Notice message={task.error} kind="error" /><Notice message={notice} kind="success" />
    <Columns><Column>
      <Card><View style={layout.row}>
        <View style={styles.avatar}><Text style={styles.initials}>{initials}</Text></View>
        <View style={layout.flex}><Heading>{name}</Heading><Body muted>@{actor?.username}</Body></View>
      </View><Pill label={roleLabels[actor?.role || ''] || 'Team member'} />
        <View style={layout.divider} /><Heading>Current store</Heading>
        <View style={layout.row}><Ionicons name="storefront-outline" color={colors.forest} size={24} />
          <View style={layout.flex}><Body>{store?.storeName || 'Current store'}</Body></View></View>
        {stores.length > 1 ? <Button title={choosingStore ? 'Close store list' : 'Switch store'} variant="secondary" icon="swap-horizontal"
          disabled={task.pending || busy} onPress={() => setChoosingStore(!choosingStore)} /> : null}
        {choosingStore ? <View style={layout.smallGap}>{stores.map((item) => <Pressable key={item.storeId}
          accessibilityRole="button" accessibilityLabel={`Switch to ${item.storeName}`}
          accessibilityState={{ selected: item.storeId === actor?.storeId, disabled: task.pending || busy }}
          disabled={task.pending || busy} onPress={() => chooseStore(item.storeId, item.storeName)}
          style={({ pressed }) => [styles.storeOption, item.storeId === actor?.storeId && { backgroundColor: colors.sage }, pressed && { opacity: 0.7 }]}>
          <View style={layout.flex}><Text style={styles.storeName}>{item.storeName}</Text>
            <Text style={styles.meta}>{roleLabels[item.role] || 'Team member'}</Text></View>
          <Ionicons name={item.storeId === actor?.storeId ? 'checkmark-circle' : 'chevron-forward'} color={colors.forest} size={22} />
        </Pressable>)}</View> : null}
      </Card>
      <Card><Heading>Your access at this store</Heading><Body muted>Access is set by your account administrator and can differ between stores.</Body>
        {actor?.capabilities.length ? actor.capabilities.map((capability) => <View key={capability} style={layout.row}>
          <Ionicons name="checkmark-circle-outline" color={colors.forest} size={22} />
          <View style={layout.flex}><Body>{permissionLabels[capability] || 'Workspace access'}</Body></View>
        </View>) : <Body muted>No module permissions are assigned at this store.</Body>}
      </Card>
    </Column><Column>
      <Card><Heading>Sign-in & security</Heading><Body muted>Keep your account personal, even when devices are shared.</Body>
        {changingPassword ? <View style={layout.gap}>
          <Field label="Current password" value={currentPassword} onChangeText={setCurrentPassword} secureTextEntry
            autoCapitalize="none" autoCorrect={false} textContentType="password" autoComplete="current-password" maxLength={1024}
            returnKeyType="next" submitBehavior="submit" onSubmitEditing={() => newPasswordInput.current?.focus()} />
          <Field label="New password" value={newPassword} onChangeText={setNewPassword} secureTextEntry
            autoCapitalize="none" autoCorrect={false} textContentType="newPassword" autoComplete="new-password" maxLength={1024} hint="Use at least 8 characters."
            inputRef={newPasswordInput} returnKeyType="next" submitBehavior="submit" onSubmitEditing={() => confirmationInput.current?.focus()} />
          <Field label="Confirm new password" value={confirmation} onChangeText={setConfirmation} secureTextEntry
            autoCapitalize="none" autoCorrect={false} textContentType="newPassword" autoComplete="new-password" maxLength={1024}
            returnKeyType="done" onSubmitEditing={savePassword} inputRef={confirmationInput} />
          <Button title="Save password" onPress={savePassword} loading={task.pending || busy} disabled={!currentPassword || newPassword.length < 8 || !confirmation} />
          <Button title="Cancel password change" variant="quiet" disabled={task.pending || busy} onPress={() => {
            setChangingPassword(false); setCurrentPassword(''); setNewPassword(''); setConfirmation(''); task.setError(null);
          }} />
        </View> : <Button title="Change password" variant="secondary" icon="key-outline" disabled={task.pending || busy} onPress={() => {
          setChangingPassword(true); setNotice(null); task.setError(null);
        }} />}
        <View style={layout.divider} />
        <Button title="Sign out of this device" variant="secondary" icon="log-out-outline" loading={task.pending || busy} onPress={() => { void task.run(() => signOut()); }} />
        <Button title="Sign out on every device" variant="danger" disabled={task.pending || busy} onPress={signOutEverywhere} />
      </Card>
      {actor?.capabilities.includes('memberships.manage') ? <TeamCard storeId={actor.storeId} ownUserId={actor.userId} />
        : <Card style={{ backgroundColor: colors.sage }}><Heading>Need different access?</Heading>
          <Body>Your store manager or account administrator can help update your team permissions.</Body></Card>}
    </Column></Columns>
  </Screen>;
}

function TeamCard({ storeId, ownUserId }: { storeId: number; ownUserId: number }) {
  const resource = useResource<{ storeId: number; members: TeamMember[] }>('/accounts/team');
  const mismatch = resource.data !== null && resource.data.storeId !== storeId;
  const members = mismatch ? [] : resource.data?.members || [];
  return <Card><View style={layout.row}><Ionicons name="people-outline" color={colors.forest} size={24} /><Heading>Your store team</Heading></View>
    <Body muted>View team access here. Invitations, permission changes, and account administration remain available in the web workspace.</Body>
    {resource.loading ? <Loading label="Loading your team…" />
      : resource.error || mismatch ? <Notice kind="error" message={resource.error || 'Your selected store changed. Reload the team to continue.'} />
      : members.length === 0 ? <EmptyState icon="people-outline" title="A team starts here" description="There are no store memberships to show." />
        : members.map((member) => <View key={member.userId} style={styles.member}>
          <View style={layout.smallGap}><Text style={styles.storeName}>{member.displayName || member.username}{member.userId === ownUserId ? ' (you)' : ''}</Text>
            <Text style={styles.meta}>@{member.username} · {member.businessRole === 'owner' && member.businessState === 'active' ? 'Business owner' : roleLabels[member.role] || 'Team member'}</Text>
            <Pill label={member.accountState === 'pending' ? 'Awaiting activation' : member.accountState === 'suspended' ? 'Suspended' : member.membershipState === 'revoked' ? 'Store access removed' : 'Active'} />
            {member.businessRole === 'admin' && member.businessState === 'active' ? <Body muted>Business administrator delegation</Body> : null}
          </View>
        </View>)}
    <Button title="Refresh team" variant="secondary" icon="refresh-outline" loading={resource.loading} onPress={() => { void resource.refresh(); }} />
  </Card>;
}

const styles = StyleSheet.create({
  avatar: { width: 64, height: 64, borderRadius: 22, backgroundColor: colors.peach, justifyContent: 'center', alignItems: 'center' },
  initials: { color: colors.ink, fontSize: 23, fontWeight: '700' },
  storeOption: { minHeight: 68, padding: 15, borderRadius: 15, borderWidth: 1, borderColor: colors.line, flexDirection: 'row', alignItems: 'center', gap: 12 },
  storeName: { color: colors.ink, fontSize: 16, fontWeight: '600', lineHeight: 23 },
  meta: { color: colors.muted, fontSize: 13, lineHeight: 20, marginTop: 4 },
  member: { borderBottomWidth: 1, borderBottomColor: colors.line, paddingVertical: 16 },
});
