import { Text } from '@/src/ui/Typography';
import React, { useState } from 'react';
import { Alert, Pressable, StyleSheet, View } from 'react-native';
import { useRouter } from 'expo-router';
import Ionicons from '@expo/vector-icons/Ionicons';
import { useSession } from '@/src/session/SessionProvider';
import { Body, Button, Card, Field, Heading, Loading, Notice, Screen, layout } from '@/src/ui/components';
import { colors, permissionLabels, roleLabels } from '@/src/ui/theme';
import { useResource } from '@/src/ui/useResource';
import type { Invitation, Management, RoleChoice } from './types';

export type AdminContext = { data: Management; storeName: string; changed: (message: string) => Promise<void> };
export function AdministrationScreen({ title, ownerOnly = false, children }: {
  title: string; ownerOnly?: boolean; children: (context: AdminContext) => React.ReactNode;
}) {
  const { actor, stores } = useSession();
  const router = useRouter();
  const allowed = Boolean(actor?.capabilities.includes('memberships.manage') && (!ownerOnly || actor.role === 'owner'));
  const resource = useResource<Management>('/accounts/management', allowed);
  const [notice, setNotice] = useState<string | null>(null);
  const storeName = stores.find(store => store.storeId === actor?.storeId)?.storeName || 'Current store';
  const mismatch = resource.data && (resource.data.storeId !== actor?.storeId || (ownerOnly && !resource.data.isOwner));
  return <Screen title={title} eyebrow={ownerOnly ? 'Owner workspace' : 'Team & access'} subtitle={storeName}>
    <Button title="Back" icon="arrow-back" variant="quiet" onPress={() => router.canGoBack() ? router.back() : router.replace('/accounts')} />
    <Notice message={notice} kind="success" />
    {!allowed ? <Card><Heading>Access is limited</Heading><Body>Your current account does not have permission to manage this area.</Body></Card>
      : resource.loading ? <Loading label="Checking team access…" />
      : resource.error || mismatch ? <Card><Notice kind="error" message={resource.error || 'Your store changed. Reload to continue.'} />
        <Button title="Reload team" onPress={() => { void resource.refresh(); }} /></Card>
      : resource.data ? children({ data: resource.data, storeName, changed: async message => { setNotice(message); await resource.refresh(); } }) : null}
  </Screen>;
}
export function confirmChange(title: string, message: string, action: () => void, destructive = false) {
  Alert.alert(title, message, [{ text: 'Cancel', style: 'cancel' },
    { text: 'Confirm', style: destructive ? 'destructive' : 'default', onPress: action }]);
}
export function Choice({ label, hint, selected, onPress, disabled = false, checkbox = false }: {
  label: string; hint?: string; selected: boolean; onPress: () => void; disabled?: boolean; checkbox?: boolean;
}) {
  return <Pressable accessibilityRole={checkbox ? 'checkbox' : 'radio'} accessibilityLabel={label}
    accessibilityState={{ checked: selected, disabled }} disabled={disabled} onPress={onPress}
    style={({ pressed }) => [styles.choice, selected && { backgroundColor: colors.blush, borderColor: colors.primary }, pressed && { opacity: 0.7 }]}>
    <Ionicons name={selected ? 'checkmark-circle' : 'ellipse-outline'} size={24} color={disabled ? colors.muted : colors.primary} />
    <View style={layout.flex}><Text style={styles.label}>{label}</Text>{hint ? <Text style={styles.hint}>{hint}</Text> : null}</View>
  </Pressable>;
}
export function Roles({ choices, value, onChange, disabled }: {
  choices: RoleChoice[]; value: string; onChange: (role: string) => void; disabled?: boolean;
}) {
  return <View style={layout.smallGap}><Heading>Store role</Heading>{choices.map(choice => <Choice key={choice.role}
    label={roleLabels[choice.role] || choice.role} selected={value === choice.role} disabled={disabled} onPress={() => onChange(choice.role)} />)}</View>;
}
export function Permissions({ included = [], optional, value, onChange, disabled }: {
  included?: string[]; optional: string[]; value: string[]; onChange: (value: string[]) => void; disabled?: boolean;
}) {
  return <View style={layout.smallGap}><Heading>Permissions</Heading>
    <Body muted>Inventory permissions take effect as those modules become available.</Body>
    {included.map(capability => <Choice key={capability} label={permissionLabels[capability] || capability}
      hint="Included with this role" selected disabled checkbox onPress={() => undefined} />)}
    {optional.map(capability => <Choice key={capability} label={permissionLabels[capability] || capability}
      selected={value.includes(capability)} checkbox disabled={disabled}
      onPress={() => onChange(value.includes(capability) ? value.filter(item => item !== capability) : [...value, capability])} />)}
    {!included.length && !optional.length ? <Body muted>No permissions can be assigned for this role.</Body> : null}
  </View>;
}
export function Reason({ value, onChange, disabled }: { value: string; onChange: (value: string) => void; disabled?: boolean }) {
  return <Field label="Reason (optional)" value={value} onChangeText={onChange} maxLength={500} editable={!disabled}
    multiline style={{ minHeight: 90 }} hint="Recorded with this account change." />;
}
export function InvitationResult({ invitation, username, onDismiss }: {
  invitation: Invitation; username: string; onDismiss: () => void;
}) {
  return <Card><Heading>Invitation ready</Heading><Body>Give this activation code only to @{username}. It expires in {Math.round(invitation.expiresIn / 3600)} hours.</Body>
    <Text selectable style={styles.code} accessibilityLabel={`Activation code: ${invitation.token}`}>{invitation.token}</Text>
    <Body muted>On the sign-in screen, choose Activate account, enter this code, and set a personal password. This code is hidden when you leave this screen or background the app. Reissue it if needed.</Body>
    <Button title="Done with this code" onPress={onDismiss} />
  </Card>;
}
const styles = StyleSheet.create({
  choice: { minHeight: 56, borderWidth: 1, borderColor: colors.controlLine, borderRadius: 14, padding: 14, flexDirection: 'row', alignItems: 'center', gap: 12 },
  label: { fontSize: 16, fontWeight: '600', color: colors.ink }, hint: { fontSize: 13, lineHeight: 20, color: colors.muted, marginTop: 4 },
  code: { color: colors.ink, backgroundColor: colors.soft, borderRadius: 12, padding: 16, fontSize: 18, lineHeight: 28, fontFamily: 'monospace' },
});
