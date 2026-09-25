import React, { useEffect, useRef, useState } from 'react';
import { Redirect, useLocalSearchParams, useRouter } from 'expo-router';
import { TextInput, View } from 'react-native';
import { useSession } from '@/src/session/SessionProvider';
import { Body, Brand, Button, Card, Column, Columns, Field, Heading, Loading, Notice, Screen, layout } from '@/src/ui/components';
import { useTask } from '@/src/ui/useTask';
import { invitationToken, type InvitationDetails } from '@/src/accounts/invitations';
import { colors } from '@/src/ui/theme';
import { useSensitiveForm } from '@/src/ui/useSensitiveForm';

export function SignInScreen() {
  const { status, signIn, message, busy } = useSession();
  const router = useRouter();
  const task = useTask();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const usernameInput = useRef<TextInput>(null);
  const passwordInput = useRef<TextInput>(null);
  useSensitiveForm(() => setPassword(''));
  if (status === 'ready' || status === 'locked') return <Redirect href="/today" />;
  if (status === 'loading') return <Loading label="Opening Shiftly…" />;
  const submit = () => { void task.run(async () => {
    const secret = password;
    setPassword('');
    await signIn({ username: username.trim(), password: secret });
  }); };
  return <Screen title="A better handoff.
A calmer shift." subtitle="Your people, your store, and everything the next shift needs to know.">
    <Brand />
    <Columns><Column><Card>
      <Heading>Welcome back</Heading><Body muted>Sign in with your individual account.</Body>
      <Notice message={task.error || message} kind={task.error ? 'error' : 'info'} />
      <Field label="Username" value={username} onChangeText={setUsername} autoCapitalize="none"
        autoCorrect={false} autoComplete="username" textContentType="username" maxLength={80}
        placeholder="Your username" returnKeyType="next" inputRef={usernameInput}
        submitBehavior="submit" onSubmitEditing={() => passwordInput.current?.focus()} />
      <Field label="Password" value={password} onChangeText={setPassword} secureTextEntry inputRef={passwordInput}
        autoCapitalize="none" autoCorrect={false} autoComplete="current-password" textContentType="password"
        maxLength={1024} returnKeyType="go" onSubmitEditing={submit} />
      <Button title="Sign in" icon="arrow-forward" onPress={submit} loading={task.pending || busy}
        disabled={!username.trim() || !password} />
      <Button title="Activate or recover an account" variant="quiet" onPress={() => router.push('/activate')} />
    </Card></Column>
    <Column><Card style={{ backgroundColor: colors.soft, borderColor: colors.soft }}>
      <Heading>Good shifts start with a clear picture.</Heading>
      <Body>Leave a useful handoff, catch up on your team's reports, and keep your store in sync.</Body>
      <View style={layout.divider} />
      <Body muted>New to the team? Ask your manager for an invitation link to set up your own account.</Body>
    </Card></Column></Columns>
  </Screen>;
}

export function ActivateScreen() {
  const { status, activate, resetPassword, invitationDetails, signOut, busy } = useSession();
  const router = useRouter();
  const task = useTask();
  const [mode, setMode] = useState<'activate' | 'recover'>('activate');
  const params = useLocalSearchParams<{ '#': string }>();
  const [token, setToken] = useState(() => invitationToken(params['#']));
  const [details, setDetails] = useState<InvitationDetails | null>(null);
  useEffect(() => {
    if (!params['#']) return;
    setToken(invitationToken(params['#']));
    router.setParams({ '#': '' });
  }, [params['#'], router]);
  useEffect(() => {
    let current = true;
    setDetails(null);
    const timer = setTimeout(() => {
      if (mode === 'activate' && token.trim().length === 43) {
        void invitationDetails(token.trim()).then(value => { if (current) setDetails(value); }).catch(() => undefined);
      }
    }, 400);
    return () => { current = false; clearTimeout(timer); };
  }, [mode, token, invitationDetails]);
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [complete, setComplete] = useState(false);
  const passwordInput = useRef<TextInput>(null);
  const confirmationInput = useRef<TextInput>(null);
  useSensitiveForm(() => { setToken(''); setPassword(''); setConfirmation(''); setDetails(null); });
  if (status === 'ready' && (complete || task.pending)) return <Redirect href="/today" />;
  if (status === 'ready' || status === 'locked') return <Screen title="An invitation for a new account">
    <Card><Body>Sign out of your current account before activating this invitation.</Body>
      <Button title="Sign out to activate" onPress={() => { void signOut(); }} />
      <Button title="Keep my current account" variant="secondary" onPress={() => router.replace('/today')} /></Card>
  </Screen>;
  if (status === 'loading') return <Loading />;
  const changeMode = (value: 'activate' | 'recover') => {
    setMode(value); setToken(''); setPassword(''); setConfirmation(''); setComplete(false); task.setError(null);
  };
  const submit = () => {
    if (password !== confirmation) { task.setError('Your passwords do not match.'); return; }
    void task.run(async () => {
      const credentials = { token: token.trim(), password };
      setPassword(''); setConfirmation(''); setToken('');
      await (mode === 'activate' ? activate(credentials) : resetPassword(credentials));
    }, () => setComplete(true));
  };
  return <Screen title={mode === 'activate' ? 'Make it yours.' : 'A fresh start.'} eyebrow="Your Shiftly account"
    subtitle="Use the private invitation link or code given to you by your manager or account administrator.">
    <Columns><Column><Card>
      <View style={layout.wrap}>
        <Button title="Activate account" variant={mode === 'activate' ? 'primary' : 'secondary'} onPress={() => changeMode('activate')} disabled={task.pending || busy} />
        <Button title="Reset password" variant={mode === 'recover' ? 'primary' : 'secondary'} onPress={() => changeMode('recover')} disabled={task.pending || busy} />
      </View>
      {complete ? <><Notice kind="success" message={mode === 'activate' ? 'Your account is ready. Sign in with your username and password.' : 'Your password has been reset. Sign in with your new password.'} />
        <Button title="Back to sign in" onPress={() => router.replace('/sign-in')} /></> : <>
        <Notice message={task.error} kind="error" />
        {details ? <Notice message={`Join ${details.storeName} as @${details.username}. Your account starts as crew.`} /> : null}
        <Field label={mode === 'activate' ? 'Invitation code' : 'Recovery code'} value={token} onChangeText={setToken}
          autoCapitalize="none" autoCorrect={false} secureTextEntry maxLength={1024} returnKeyType="next"
          submitBehavior="submit" onSubmitEditing={() => passwordInput.current?.focus()} />
        <Field label="New password" value={password} onChangeText={setPassword} secureTextEntry
          autoCapitalize="none" autoCorrect={false} autoComplete="new-password" textContentType="newPassword" maxLength={1024}
          hint="Use at least 8 characters." inputRef={passwordInput} returnKeyType="next"
          submitBehavior="submit" onSubmitEditing={() => confirmationInput.current?.focus()} />
        <Field label="Confirm new password" value={confirmation} onChangeText={setConfirmation} secureTextEntry
          autoCapitalize="none" autoCorrect={false} autoComplete="new-password" textContentType="newPassword" maxLength={1024}
          returnKeyType="done" onSubmitEditing={submit} inputRef={confirmationInput} />
        <Button title={mode === 'activate' ? 'Activate my account' : 'Save new password'} onPress={submit}
          loading={task.pending || busy} disabled={!token.trim() || password.length < 8 || !confirmation} />
        <Button title="Back to sign in" variant="quiet" onPress={() => router.replace('/sign-in')} />
      </>}
    </Card></Column><Column><Card style={{ backgroundColor: colors.soft, borderColor: colors.soft }}>
      <Heading>A code just for you</Heading><Body>Codes can be used once and expire. If yours no longer works, ask {mode === 'activate' ? 'your manager' : 'your account administrator or operator'} for a replacement.</Body>
      <Body muted>Keep your code private. Your password belongs to you and is never shared with your team.</Body>
    </Card></Column></Columns>
  </Screen>;
}
