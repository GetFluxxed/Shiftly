import { Text } from '@/src/ui/Typography';
import React from 'react';
import { useRouter } from 'expo-router';
import { Pressable, StyleSheet, View } from 'react-native';
import Ionicons from '@expo/vector-icons/Ionicons';
import { useSession } from '@/src/session/SessionProvider';
import { Body, Button, Card, Column, Columns, EmptyState, Heading, Loading, Notice, Pill, Screen, layout } from '@/src/ui/components';
import { colors, fonts, friendlyDate, roleLabels } from '@/src/ui/theme';
import { useResource } from '@/src/ui/useResource';

type HeadsUp = { message: string; updatedAt?: string | null };

export function TodayScreen() {
  const { actor, stores } = useSession();
  const router = useRouter();
  const can = (permission: string) => Boolean(actor?.capabilities.includes(permission));
  const reports = can('reports.view') || can('reports.submit');
  const resource = useResource<HeadsUp>('/heads-up', reports);
  const store = stores.find((item) => item.storeId === actor?.storeId);
  const firstName = (actor?.displayName || actor?.username || 'there').split(' ')[0];
  const hour = new Date().getHours();
  const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening';
  return <Screen title={`${greeting},\n${firstName}.`} eyebrow={new Date().toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' })}
    subtitle="A little clarity for the shift ahead.">
    <Card style={styles.storeCard}>
      <View style={layout.row}><Ionicons name="storefront-outline" size={25} color={colors.onPrimary} />
        <View style={layout.flex}><Text style={styles.storeLabel}>YOUR WORKSPACE</Text>
          <Text style={styles.storeName}>{store?.storeName || 'Current store'}</Text></View>
      </View>
      <View style={[layout.wrap, { alignItems: 'center', justifyContent: 'space-between' }]}>
        <Text style={styles.storeDescription}>{actor?.displayName || actor?.username}</Text>
        <Pill label={roleLabels[actor?.role || ''] || 'Team member'} />
      </View>
      {stores.length > 1 ? <Pressable accessibilityRole="button" accessibilityLabel="Change your store" onPress={() => router.push('/accounts')}
        style={({ pressed }) => [styles.storeSwitch, pressed && { opacity: 0.7 }]}>
        <Text style={styles.storeSwitchText}>Change store</Text><Ionicons name="swap-horizontal" size={20} color={colors.onPrimary} />
      </Pressable> : null}
    </Card>
    <Columns><Column>
      <Card>
        {reports ? <Button title={can('reports.view') ? 'Read shift reports' : 'Write a shift report'} icon={can('reports.view') ? 'reader-outline' : 'create-outline'} onPress={() => router.push('/reports')} /> : null}
        <Heading>Make the next shift easier.</Heading>
        <Body muted>{can('reports.view') ? 'Catch up on the details your team left behind.' : can('reports.submit') ? 'A few thoughtful notes can make all the difference.' : 'Your workspace reflects the access your team has shared with you.'}</Body>
        {can('inventory.view') ? <Button title="Visit inventory" variant="secondary" icon="cube-outline" onPress={() => router.push('/inventory')} /> : null}
        {can('memberships.manage') ? <Button title={actor?.role === 'owner' ? 'Owner workspace' : 'Manage your team'} variant="secondary" icon="people-outline" onPress={() => router.push(actor?.role === 'owner' ? '/owner' : '/team')} /> : null}
        <Button title="Your account & access" variant="quiet" icon="person-circle-outline" onPress={() => router.push('/accounts')} />
      </Card>
    </Column><Column>
      {reports ? <Card>
        <View style={layout.row}><Ionicons name="megaphone-outline" color={colors.accentStrong} size={24} /><Heading>Heads up</Heading></View>
        {resource.loading ? <Loading label="Getting the latest update…" /> : resource.error ? <>
          <Notice message={resource.error} kind="error" /><Button title="Retry update" variant="secondary" onPress={() => { void resource.refresh(); }} />
        </> : <>
          {resource.data?.message ? <><Body>{resource.data.message}</Body>
            {resource.data.updatedAt ? <Body muted>Updated {friendlyDate(resource.data.updatedAt)}</Body> : null}</>
            : <EmptyState icon="chatbubble-ellipses-outline" title="All clear for now" description="There are no store updates to show. Check here for a note from your manager." />}
          <Button title="Refresh update" variant="quiet" onPress={() => { void resource.refresh(); }} />
        </>}
      </Card> : <Card style={{ backgroundColor: colors.soft }}><Heading>One team. Your own account.</Heading>
        <Body>Find your store access, change your password, and keep your account up to date.</Body></Card>}
    </Column></Columns>
  </Screen>;
}

const styles = StyleSheet.create({
  storeCard: { backgroundColor: colors.primary, borderColor: colors.primary, gap: 16 },
  storeLabel: { color: colors.onPrimaryMuted, fontSize: 11, letterSpacing: 1.5, fontWeight: '700', marginBottom: 7 },
  storeName: { color: colors.onPrimary, fontFamily: fonts.display, fontSize: 30, lineHeight: 34 },
  storeDescription: { color: colors.onPrimaryMuted, fontSize: 15, lineHeight: 23 },
  storeSwitch: { minHeight: 48, alignSelf: 'flex-start', flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 10, paddingHorizontal: 16, borderRadius: 24, borderWidth: 1, borderColor: colors.onPrimaryMuted },
  storeSwitchText: { color: colors.onPrimary, fontSize: 15, fontWeight: '700' },
});
