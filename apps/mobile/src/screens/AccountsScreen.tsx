import Ionicons from '@expo/vector-icons/Ionicons';
import { useRouter } from 'expo-router';
import React, { useRef, useState } from 'react';
import { Alert, Pressable, StyleSheet, TextInput, View } from 'react-native';

import { useSession } from '@/src/session/SessionProvider';
import { ActionGrid, ActionTile } from '@/src/ui/ActionGrid';
import { Text } from '@/src/ui/Typography';
import { Body, Button, Card, Field, Heading, Notice, Screen, layout } from '@/src/ui/components';
import { colors, fonts, permissionLabels, roleLabels } from '@/src/ui/theme';
import { useSensitiveForm } from '@/src/ui/useSensitiveForm';
import { useTask } from '@/src/ui/useTask';

type Panel = 'store' | 'permissions' | 'security' | 'signOut' | null;

export function AccountsScreen() {
  const router = useRouter();
  const { actor, stores, switchStore, changePassword, signOut, busy } = useSession();
  const task = useTask();
  const [panel, setPanel] = useState<Panel>(null);
  const [changingPassword, setChangingPassword] = useState(false);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [notice, setNotice] = useState<string | null>(null);
  const newPasswordInput = useRef<TextInput>(null);
  const confirmationInput = useRef<TextInput>(null);
  const clearPasswordForm = () => {
    setCurrentPassword('');
    setNewPassword('');
    setConfirmation('');
    setChangingPassword(false);
  };
  useSensitiveForm(clearPasswordForm);

  const store = stores.find((item) => item.storeId === actor?.storeId);
  const name = actor?.displayName || actor?.username || 'Your account';
  const initials = name.split(' ').slice(0, 2).map((part) => part[0]).join('').toUpperCase();
  const canSwitchStore = ['owner', 'admin'].includes(actor?.role || '') && stores.length > 1;
  const canAdministerTeam = actor?.role === 'admin' && actor.capabilities.includes('memberships.manage');
  const unavailable = task.pending || busy;

  const openPanel = (nextPanel: Exclude<Panel, null>) => {
    if (panel === 'security' && nextPanel !== 'security') clearPasswordForm();
    task.setError(null);
    setNotice(null);
    setPanel(nextPanel);
  };
  const closePanel = () => {
    if (panel === 'security') clearPasswordForm();
    task.setError(null);
    setPanel(null);
  };
  const chooseStore = (storeId: number, storeName: string) => {
    if (!canSwitchStore || storeId === actor?.storeId) return;
    Alert.alert(`Switch to ${storeName}?`, 'Your workspace will reload for this store. Unsent notes will be cleared.', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Switch store', onPress: () => { void task.run(() => switchStore(storeId)); } },
    ]);
  };
  const savePassword = () => {
    if (unavailable || !currentPassword || newPassword.length < 8 || !confirmation) return;
    if (newPassword !== confirmation) {
      task.setError('Your new passwords do not match.');
      return;
    }
    void task.run(async () => {
      const previous = currentPassword;
      const next = newPassword;
      clearPasswordForm();
      await changePassword(previous, next);
    }, () => { setNotice('Your password was changed.'); });
  };
  const signOutEverywhere = () => Alert.alert(
    'Sign out on every device?',
    'All sessions for your account will end, including this one. You can sign in again with your password.',
    [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Sign out everywhere', style: 'destructive', onPress: () => { void task.run(() => signOut(true)); } },
    ],
  );

  return <Screen title="Account">
    <Notice message={task.error} kind="error" />
    <Notice message={notice} kind="success" />

    <Card style={styles.identityCard}>
      <View style={layout.row}>
        <View style={styles.avatar}><Text style={styles.initials}>{initials}</Text></View>
        <View style={layout.flex}>
          <Heading>{name}</Heading>
          <Body muted>@{actor?.username} · Account ID {actor?.userId}</Body>
          <Text style={styles.context}>{store?.storeName || 'Current store'} · {roleLabels[actor?.role || ''] || 'Team member'}</Text>
        </View>
      </View>
    </Card>

    {panel === null ? <>
      <ActionGrid>
        <ActionTile
          title={canSwitchStore ? 'Switch store' : 'Current store'}
          icon={canSwitchStore ? 'swap-horizontal-outline' : 'storefront-outline'}
          onPress={() => openPanel('store')}
          disabled={unavailable}
        />
        <ActionTile title="View permissions" icon="key-outline"
          onPress={() => openPanel('permissions')} disabled={unavailable} />
        <ActionTile title="Sign-in & security" icon="shield-checkmark-outline"
          onPress={() => openPanel('security')} disabled={unavailable} />
        <ActionTile title="Sign Out" icon="log-out-outline"
          onPress={() => openPanel('signOut')} disabled={unavailable} />
      </ActionGrid>
      {canAdministerTeam ? <Pressable accessibilityRole="link" accessibilityLabel="Team administration"
        disabled={unavailable} onPress={() => router.push('/team')}
        style={({ pressed }) => [styles.adminLink, unavailable && styles.disabled, pressed && styles.pressed]}>
        <Ionicons name="people-outline" color={colors.primary} size={20} />
        <Text style={styles.adminLinkText}>Team administration</Text>
        <Ionicons name="chevron-forward" color={colors.primary} size={18} />
      </Pressable> : null}
    </> : <View style={layout.gap}>
      {panel !== 'signOut' ? <Button title="Back to settings" variant="quiet" icon="arrow-back" disabled={unavailable} onPress={closePanel} /> : null}

      {panel === 'store' ? <Card>
        <Heading>{canSwitchStore ? 'Switch store' : 'Current store'}</Heading>
        <Body muted>{canSwitchStore
          ? 'Choose the store you want to work in. Your role and permissions may differ by store.'
          : 'This is the store assigned to your account.'}</Body>
        {canSwitchStore ? <View style={layout.smallGap}>{stores.map((item) => <Pressable key={item.storeId}
          accessibilityRole="button" accessibilityLabel={`Switch to ${item.storeName}`}
          accessibilityState={{ selected: item.storeId === actor?.storeId, disabled: unavailable }}
          disabled={unavailable} onPress={() => chooseStore(item.storeId, item.storeName)}
          style={({ pressed }) => [styles.storeOption, item.storeId === actor?.storeId && styles.selectedStore,
            unavailable && styles.disabled, pressed && styles.pressed]}>
          <View style={layout.flex}>
            <Text style={styles.storeName}>{item.storeName}</Text>
            <Text style={styles.meta}>{roleLabels[item.role] || 'Team member'}</Text>
          </View>
          <Ionicons name={item.storeId === actor?.storeId ? 'checkmark-circle' : 'chevron-forward'} color={colors.primary} size={22} />
        </Pressable>)}</View> : <View style={styles.storeSummary}>
          <Ionicons name="storefront-outline" color={colors.primary} size={24} />
          <View style={layout.flex}>
            <Body>{store?.storeName || 'Current store'}</Body>
            <Text style={styles.meta}>{roleLabels[actor?.role || ''] || 'Team member'}</Text>
          </View>
        </View>}
      </Card> : null}

      {panel === 'permissions' ? <Card>
        <Heading>Your access at this store</Heading>
        <Body muted>Access is set by your account administrator and can differ between stores.</Body>
        {actor?.capabilities.length ? actor.capabilities.map((capability) => <View key={capability} style={layout.row}>
          <Ionicons name="checkmark-circle-outline" color={colors.primary} size={22} />
          <View style={layout.flex}><Body>{permissionLabels[capability] || 'Workspace access'}</Body></View>
        </View>) : <Body muted>No module permissions are assigned at this store.</Body>}
      </Card> : null}

      {panel === 'security' ? <Card>
        <Heading>Sign-in & security</Heading>
        <Body muted>Keep your account personal, even when devices are shared.</Body>
        {changingPassword ? <View style={layout.gap}>
          <Field label="Current password" value={currentPassword} onChangeText={setCurrentPassword} secureTextEntry
            autoCapitalize="none" autoCorrect={false} textContentType="password" autoComplete="current-password" maxLength={1024}
            editable={!unavailable}
            returnKeyType="next" submitBehavior="submit" onSubmitEditing={() => newPasswordInput.current?.focus()} />
          <Field label="New password" value={newPassword} onChangeText={setNewPassword} secureTextEntry
            autoCapitalize="none" autoCorrect={false} textContentType="newPassword" autoComplete="new-password" maxLength={1024}
            editable={!unavailable}
            hint="Use at least 8 characters." inputRef={newPasswordInput} returnKeyType="next" submitBehavior="submit"
            onSubmitEditing={() => confirmationInput.current?.focus()} />
          <Field label="Confirm new password" value={confirmation} onChangeText={setConfirmation} secureTextEntry
            autoCapitalize="none" autoCorrect={false} textContentType="newPassword" autoComplete="new-password" maxLength={1024}
            editable={!unavailable}
            returnKeyType="done" onSubmitEditing={savePassword} inputRef={confirmationInput} />
          <Button title="Save password" onPress={savePassword} loading={unavailable}
            disabled={!currentPassword || newPassword.length < 8 || !confirmation} />
          <Button title="Cancel password change" variant="quiet" disabled={unavailable} onPress={() => {
            clearPasswordForm();
            task.setError(null);
          }} />
        </View> : <Button title="Change password" variant="secondary" icon="key-outline" disabled={unavailable} onPress={() => {
          setChangingPassword(true);
          setNotice(null);
          task.setError(null);
        }} />}
        <View style={layout.divider} />
        <Button title="Sign out on every device" variant="danger" disabled={unavailable} onPress={signOutEverywhere} />
      </Card> : null}

      {panel === 'signOut' ? <Card>
        <Heading>Sign out of this device?</Heading>
        <Body muted>You will need your username and password to sign in again.</Body>
        <Button title="Sign Out" variant="danger" loading={unavailable} onPress={() => { void task.run(() => signOut()); }} />
        <Button title="Cancel Sign Out" variant="quiet" disabled={unavailable} onPress={closePanel} />
      </Card> : null}
    </View>}
  </Screen>;
}

const styles = StyleSheet.create({
  identityCard: { padding: 18 },
  avatar: { width: 56, height: 56, borderRadius: 28, backgroundColor: colors.blush, justifyContent: 'center', alignItems: 'center' },
  initials: { color: colors.primary, fontFamily: fonts.display, fontSize: 24 },
  context: { color: colors.ink, fontSize: 14, lineHeight: 21, marginTop: 5, fontWeight: '600' },
  storeOption: { minHeight: 68, padding: 15, borderRadius: 15, borderWidth: 1, borderColor: colors.line, flexDirection: 'row', alignItems: 'center', gap: 12 },
  selectedStore: { backgroundColor: colors.soft },
  storeSummary: { minHeight: 68, padding: 15, borderRadius: 15, backgroundColor: colors.soft, flexDirection: 'row', alignItems: 'center', gap: 12 },
  storeName: { color: colors.ink, fontSize: 16, fontWeight: '600', lineHeight: 23 },
  meta: { color: colors.muted, fontSize: 13, lineHeight: 20, marginTop: 4 },
  adminLink: { minHeight: 48, alignSelf: 'center', paddingHorizontal: 14, flexDirection: 'row', alignItems: 'center', gap: 8 },
  adminLinkText: { color: colors.primary, fontSize: 15, lineHeight: 22, fontWeight: '700', flexShrink: 1 },
  disabled: { opacity: 0.55 },
  pressed: { opacity: 0.72 },
});
